"""Floor planner: DesignIntent -> BuildingSpecification.

Layout model (identical on every floor so stairs stack):

    rear ┌────────┬──────┬────────┐
         │        │ slot │        │   spine = hall (ground) or landing (upper floors),
         │ left   ├──────┤ right  │   running from the front wall towards the rear and
         │ column │spine │ column │   holding the stairs. The optional slot is a small
         │        │ ▤▤▤▤ │        │   room (WC, bathroom, store) behind it.
   front └────────┴──────┴────────┘

Every column room touches the spine (so it can be reached) and an exterior wall (so it
can have windows). Room depths are shared out in proportion to Claude's target areas.
"""

import logging
import math
from dataclasses import dataclass

from fastapi import status

from app.core.errors import AppError
from app.geometry.rect import Rect, exterior_sides
from app.geometry.stairs import calculate_stair
from app.models.building import BuildingInfo, BuildingSpecification, BuildingType, Exterior, Floor, ProjectInfo
from app.models.common import Axis, Side
from app.models.intent import DesignConstraints, DesignIntent
from app.models.materials import MaterialId, MaterialRef
from app.models.opening import DoorType
from app.models.roof import Roof, RoofType
from app.models.room import Room, RoomType
from app.models.stairs import Stair, StairDirection
from app.planner.anchor import LayoutAnchor
from app.planner.geometry import MIN_COLUMN, layout_column, min_depth, split_spine
from app.planner.layout import PRECISION, InfeasibleLayout, place_in_free_space
from app.planner.model import Box, FloorZones, Row, StairPlan
from app.planner.openings import LIVING_ROOMS, OpeningPlanner
from app.planner.site import plan_site
from app.planner.zoning import Zoning, assign_sides, floor_label, order_rows
from app.validation import ValidationReport, validate_specification
from app.validation.intent import validate_intent

logger = logging.getLogger(__name__)

SLAB = 0.25
STAIR_START = 1.4         # leaves room for a 0.9 m door off the hall in front of the stair
STAIR_START_TIGHT = 0.6
ARRIVAL_SPACE = 1.2       # clear landing beyond the top step
PASSAGE = 0.9             # clear walkway beside a stair
EXT_WALL = BuildingInfo.model_fields["wall_thickness"].default
INT_WALL = BuildingInfo.model_fields["interior_wall_thickness"].default
STAIR_CLEARANCE = 0.02    # gap between a stair and the face of the wall beside or beyond it
AREA_NOTE_THRESHOLD = 0.3
COMMERCIAL = frozenset({BuildingType.OFFICE, BuildingType.SHOP, BuildingType.APARTMENT_BUILDING})


SEARCH_STEP = 0.1         # spine positions are tried every 10 cm
STRANDED_ROOM_PENALTY = 40.0  # a room cut off from the hall or landing costs as much as badly distorting a large room


class _NeedsFiller(Exception):
    """A candidate layout would leave a column empty; skipped during the search."""


class PlanningError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("planning_failed", message, status.HTTP_422_UNPROCESSABLE_CONTENT)


@dataclass
class PlanResult:
    specification: BuildingSpecification
    report: ValidationReport
    notes: list[str]


def plan_building(intent: DesignIntent, anchor: LayoutAnchor | None = None) -> PlanResult:
    errors = [i for i in validate_intent(intent, DesignConstraints()).issues if i.severity.value == "error"]
    if errors:
        raise PlanningError("The design cannot be planned until these problems are fixed: " + " ".join(i.message for i in errors[:5]))
    return _Planner(intent, anchor).run()


class _Planner:
    def __init__(self, intent: DesignIntent, anchor: LayoutAnchor | None = None) -> None:
        self.intent = intent
        self.anchor = anchor  # keep an earlier arrangement where possible (modifications)
        self.anchored = False
        self.width = round(intent.footprint_width, PRECISION)
        self.depth = round(intent.footprint_depth, PRECISION)
        self.zoning = Zoning(intent)
        self.notes: list[str] = []
        commercial = intent.building_type in COMMERCIAL
        self.stair_width = 1.1 if commercial else 0.9
        self.stair_dims = calculate_stair(intent.floor_height, run=0.28 if commercial else 0.25)
        self.spine_width = 1.6  # set properly once the stair arrangement is known
        self.central = intent.floors >= 3

    # ------------------------------------------------------------------ pipeline
    def run(self) -> PlanResult:
        self.zoning.choose_spines()
        stair_ys = self._stair_ys(self._stair_start())
        floors = self._layout_floors(stair_ys)
        stairs = self._place_stairs(floors, stair_ys)
        openings = OpeningPlanner(self.zoning, floors, stairs, Rect(0, 0, self.width, self.depth),
                                  {f.level: self.intent.floor_height - SLAB for f in floors})
        front_door, garage, patio_room = self._openings(floors, openings)
        spec = self._assemble(floors, stairs, openings, front_door, garage, patio_room)
        self.notes += self.zoning.notes + openings.notes + self._area_notes(floors)
        result = validate_specification(spec)
        logger.info("Planned '%s': %d rooms, %s", spec.project.name, len(spec.rooms), result.report.status.value)
        return PlanResult(specification=result.specification or spec, report=result.report, notes=_dedupe(self.notes))

    def _stair_start(self) -> float:
        if self.intent.floors == 1:
            return 0.0
        needed = self.stair_dims.going_length + ARRIVAL_SPACE + EXT_WALL / 2 + STAIR_CLEARANCE
        for start in (STAIR_START, STAIR_START_TIGHT):
            if start + needed <= self.depth:
                return start
        raise PlanningError(
            f"The footprint is {self.depth:g} m deep, but a straight stair for {self.intent.floor_height:g} m floors "
            f"needs about {STAIR_START_TIGHT + needed:.1f} m. Make the building deeper."
        )

    def _stair_ys(self, start: float) -> list[float]:
        """Where each flight starts (front edge). In buildings of three or more storeys the flights
        are staggered front to rear along one wall when the footprint is deep enough, so the
        other spine wall stays free for doors on every floor."""
        flights = self.intent.floors - 1
        step = self.stair_dims.going_length + 0.1
        staggered = [round(start + k * step, PRECISION) for k in range(flights)]
        if flights >= 2 and staggered[-1] + self.stair_dims.going_length + ARRIVAL_SPACE <= self.depth:
            return staggered
        return [start] * flights

    def _central_stairs(self) -> bool:
        """Flights in the middle of the spine with a passage on each side, so neither spine wall
        is blocked. Always used from three storeys (alternating flights would block both walls);
        for two storeys the layout search chooses between this and a stair against one wall."""
        return self.central

    def _spine_width_for(self, ys: list[float]) -> float:
        if not ys:
            return 1.6
        if not self._central_stairs():
            return round(self.stair_width + PASSAGE + 0.2, PRECISION)
        side_by_side = len(set(ys)) < len(ys)
        flights_across = 2 if side_by_side else 1
        return round(flights_across * self.stair_width + 0.1 * (flights_across - 1) + 2 * PASSAGE, PRECISION)

    def _stair_sides(self, first_side: str, ys: list[float]) -> list[str]:
        if self._central_stairs():
            if len(set(ys)) == len(ys):
                return ["centre"] * len(ys)
            return ["centre_left" if k % 2 == 0 else "centre_right" for k in range(len(ys))]
        return [first_side] * len(ys)

    # ------------------------------------------------------------------ layout
    def _layout_floors(self, stair_ys: list[float]) -> list[FloorZones]:
        """Try every viable spine position, lay out all floors for each and keep the best.

        The spine must be in the same place on every floor (stairs stack), so its position is
        a building-wide choice. Each candidate is scored by how far rooms drift from their
        target areas and how awkwardly proportioned they become (see _layout_cost)."""
        if self.anchor is not None:
            floors = self._anchored_layout(stair_ys)
            if floors is not None:
                return floors
            self.notes.append("The change did not fit the existing arrangement, so the rooms were rearranged.")
        arrangements = [False, True] if self.intent.floors == 2 else [self.intent.floors >= 3]
        best: tuple[float, float, bool, bool] | None = None
        narrowest = None
        for central in arrangements:
            self.central = central
            self.spine_width = self._spine_width_for(stair_ys)
            column_width = round(self.width - self.spine_width, PRECISION)
            narrowest = narrowest or self.spine_width
            if column_width < MIN_COLUMN:
                continue
            candidates: list[tuple[float, bool]] = [(0.0, False)]
            if column_width >= 2 * MIN_COLUMN:
                steps = int(round((column_width - 2 * MIN_COLUMN) / SEARCH_STEP))
                candidates += [(round(MIN_COLUMN + i * SEARCH_STEP, PRECISION), True) for i in range(steps + 1)]
            for sx, two_columns in candidates:
                try:
                    floors = self._layout_all(sx, two_columns, stair_ys, allow_filler=False)
                except (PlanningError, _NeedsFiller):
                    continue
                cost = _layout_cost(floors) + self._access_penalty(floors, stair_ys)
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, sx, two_columns, central)

        if best is None:
            self.central = arrangements[0]
            self.spine_width = self._spine_width_for(stair_ys)
            if self.width - self.spine_width < MIN_COLUMN:
                raise PlanningError(f"The footprint is only {self.width:g} m wide; at least {(narrowest or self.spine_width) + MIN_COLUMN:.1f} m is needed.")
            # No arrangement works without a filler room; fall back to the simplest one.
            return self._layout_all(0.0, False, stair_ys, allow_filler=True)
        _, sx, two_columns, self.central = best
        self.spine_width = self._spine_width_for(stair_ys)
        logger.debug("Spine at x=%.2f, %s stair, cost %.3f", sx, "central" if self.central else "wall", best[0])
        return self._layout_all(sx, two_columns, stair_ys, allow_filler=True)

    def _anchored_layout(self, stair_ys: list[float]) -> list[FloorZones] | None:
        """The previous arrangement (spine position, sides and order of rooms) with the new intent."""
        a = self.anchor
        assert a is not None
        self.central = a.central if self.intent.floors == 2 else self.intent.floors >= 3
        self.spine_width = self._spine_width_for(stair_ys)
        right = self.width - a.spine_x - self.spine_width
        if right < MIN_COLUMN or (a.two_columns and a.spine_x < MIN_COLUMN):
            return None
        self.anchored = True
        try:
            return self._layout_all(a.spine_x, a.two_columns, stair_ys, allow_filler=False)
        except (PlanningError, _NeedsFiller):
            self.anchored = False
            return None

    def _layout_all(self, sx: float, two_columns: bool, stair_ys: list[float], allow_filler: bool) -> list[FloorZones]:
        right_x = round(sx + self.spine_width, PRECISION)
        return [
            self._layout_floor(zones, rows, sx, right_x, two_columns, stair_ys, allow_filler)
            for zones, rows in (self.zoning.zone_floor(level) for level in range(self.intent.floors))
        ]

    def _layout_floor(self, zones: FloorZones, rows: list[Row], sx: float, right_x: float,
                      two_columns: bool, stair_ys: list[float], allow_filler: bool) -> FloorZones:
        level = zones.level
        if two_columns:
            fixed = self.anchor.sides if self.anchored and self.anchor else None
            left, right = assign_sides(rows, self.zoning, (sx, self.width - right_x), self.depth, _row_min_depth, fixed)
            if not (left and right):
                if not allow_filler and len(left) + len(right) < 2:
                    raise _NeedsFiller
                left, right = self._fill_empty_column(level, left, right)
        else:
            left, right = [], rows
        if not right and not left:
            if not allow_filler:
                raise _NeedsFiller
            right = [Row(self._filler(level))]

        try:
            positions = self.anchor.positions if self.anchored and self.anchor else None
            zones.left = layout_column(order_rows(left, self.zoning, positions), 0.0, sx, self.depth, exterior_on_left=True) if left else []
            zones.right = layout_column(order_rows(right, self.zoning, positions), right_x, self.width, self.depth, exterior_on_left=False)
        except InfeasibleLayout as exc:
            raise PlanningError(
                f"The rooms on {floor_label(level)} do not fit in a {self.width:g} x {self.depth:g} m footprint "
                f"({exc}). Use fewer rooms or a larger footprint."
            ) from exc

        if not split_spine(zones, sx, self.spine_width, self.depth, self._spine_depth(level, stair_ys)):
            # The small room does not fit behind the hall: plan it as an ordinary room instead.
            slot, zones.slot = zones.slot, None
            return self._layout_floor(zones, rows + [Row(slot)], sx, right_x, two_columns, stair_ys, allow_filler)
        return zones

    def _spine_depth(self, level: int, stair_ys: list[float]) -> float:
        """How deep the hall or landing must be to hold the flight leaving it and the clear
        landing beyond the flight arriving at it."""
        needed = 0.0
        # The spine ends at a wall (interior, or the exterior rear wall); keep flights clear of its thickness.
        wall_clearance = EXT_WALL / 2 + STAIR_CLEARANCE
        for flight, y in enumerate(stair_ys):
            top = y + self.stair_dims.going_length + wall_clearance
            if flight == level:
                needed = max(needed, top)
            if flight == level - 1:
                needed = max(needed, top + ARRIVAL_SPACE)
        return needed

    def _fill_empty_column(self, level: int, left: list[Row], right: list[Row]) -> tuple[list[Row], list[Row]]:
        if left and right:
            return left, right
        full, empty = (left, right) if left else (right, left)
        if len(full) >= 2:
            smallest = min(full, key=lambda r: r.area)
            full.remove(smallest)
            empty.append(smallest)
        else:
            empty.append(Row(self._filler(level)))
        return (full, empty) if left else (empty, full)

    def _filler(self, level: int) -> Box:
        box = Box(self.zoning._unique_id(f"store_{level}"), "Store", RoomType.STORAGE, level, 6.0, glazing="none", synthetic=True)
        self.zoning.boxes[box.id] = box
        self.notes.append(f"Added a store on {floor_label(level)} to fill space no requested room needed.")
        return box

    # ------------------------------------------------------------------ stairs
    def _place_stairs(self, floors: list[FloorZones], stair_ys: list[float]) -> list[StairPlan]:
        if not stair_ys:
            return []
        sides = self._stair_sides(self._quiet_side(floors, stair_ys), stair_ys)
        stairs = []
        for level, (y, side) in enumerate(zip(stair_ys, sides)):
            spine = floors[level].spine.rect
            middle = spine.x + spine.width / 2
            left_face = (EXT_WALL if spine.x <= 1e-6 else INT_WALL) / 2 + STAIR_CLEARANCE
            right_face = (EXT_WALL if spine.x2 >= self.width - 1e-6 else INT_WALL) / 2 + STAIR_CLEARANCE
            x = {
                "left": spine.x + left_face,
                "right": spine.x2 - right_face - self.stair_width,
                "centre": middle - self.stair_width / 2,
                "centre_left": middle - 0.05 - self.stair_width,
                "centre_right": middle + 0.05,
            }[side]
            stairs.append(StairPlan(level, side, round(x, PRECISION), y, self.stair_width,
                                    self.stair_dims.risers, self.stair_dims.rise, self.stair_dims.run))
        return stairs

    def _access_penalty(self, floors: list[FloorZones], stair_ys: list[float]) -> float:
        """Rooms that would have no wall free for a door to the spine, with the stairs on their best sides."""
        if not stair_ys:
            return 0.0
        return STRANDED_ROOM_PENALTY * min(self._stranded(floors, stair_ys, side) for side in ("left", "right"))

    def _stranded(self, floors: list[FloorZones], stair_ys: list[float], first_side: str) -> int:
        """Count rooms whose whole shared wall with the spine is blocked by a flight or stairwell."""
        sides = self._stair_sides(first_side, stair_ys)
        length = self.stair_dims.going_length
        count = 0
        for zones in floors:
            blocked: dict[str, list[tuple[float, float]]] = {"left": [], "right": []}
            for flight, (y, side) in enumerate(zip(stair_ys, sides)):
                if flight in (zones.level, zones.level - 1) and side in blocked:
                    blocked[side].append((y - 0.1, y + length + 0.1))
            for side, intervals in blocked.items():
                if not intervals:
                    continue
                for row in zones.left if side == "left" else zones.right:
                    if row.is_child:
                        continue
                    a, b = max(row.main.rect.y, zones.spine.rect.y), min(row.main.rect.y2, zones.spine.rect.y2)
                    if place_in_free_space(a, b, 0.9, intervals, margin=0.15) is None:
                        count += 1
        return count

    def _quiet_side(self, floors: list[FloorZones], stair_ys: list[float]) -> str:
        """Where the first flight goes: the side that leaves the fewest rooms without a door to the spine.
        With a single column the stair goes against the exterior wall, where there are no doors."""
        if self._central_stairs() or not floors[0].left:
            return "left"
        return "left" if self._stranded(floors, stair_ys, "left") <= self._stranded(floors, stair_ys, "right") else "right"

    # ------------------------------------------------------------------ openings
    def _openings(self, floors: list[FloorZones], op: OpeningPlanner) -> tuple:
        for zones in floors:
            for row in zones.left + zones.right:
                if not row.is_child:
                    op.connect(zones.spine, row.main, self.zoning.link(zones.spine.id, row.main.id) or "door")
                for child in row.children:
                    op.connect(row.main, child)
            if zones.slot:
                op.connect(zones.spine, zones.slot)
            for row in zones.left + zones.right:
                if row.is_child:
                    parent = next((r.main for r in zones.left + zones.right if not r.is_child
                                   and self.zoning.parent_of(row.main) == r.main.id), None)
                    if parent:
                        op.connect(parent, row.main)

        boxes = self.zoning.boxes
        for pair, kind in self.zoning.links.items():
            a, b = (boxes.get(r) for r in sorted(pair))
            if a is None or b is None or a.floor != b.floor:
                continue
            if not op.connect(a, b, kind) and kind == "open":
                self.notes.append(f"{a.name} and {b.name} could not be placed side by side, so they are connected through the circulation instead.")

        ground = floors[0]
        entrance = boxes.get(self.intent.entrance_room)
        door_room = entrance if entrance and entrance.rect and Side.FRONT in exterior_sides(entrance.rect, op.footprint) else ground.spine
        prefer = None
        if door_room is ground.spine and op.stairs:
            stair = op.stairs[0]
            spine = ground.spine.rect
            prefer = (stair.x + stair.width + spine.x2) / 2 if stair.side == "left" else (spine.x + stair.x) / 2
        front_door = op.external_door(door_room, Side.FRONT, 1.0, DoorType.FRONT, prefer=prefer)
        if front_door is None:
            front_door = op.external_door(ground.spine, Side.FRONT, 0.9, DoorType.FRONT)

        garage = next((b for b in boxes.values() if b.type is RoomType.GARAGE and b.floor == 0), None)
        if garage is not None:
            wide = garage.target_area >= 28
            for side in sorted(exterior_sides(garage.rect, op.footprint), key=lambda s: [Side.FRONT, Side.LEFT, Side.RIGHT, Side.REAR].index(s)):
                if op.external_door(garage, side, 4.8 if wide else 2.4, DoorType.GARAGE):
                    break

        patio_room = None
        if self.intent.site.patio:
            living = sorted((b for b in boxes.values() if b.floor == 0 and b.type in LIVING_ROOMS),
                            key=lambda b: (Side.REAR not in exterior_sides(b.rect, op.footprint), -b.area))
            for room in living:
                sides = exterior_sides(room.rect, op.footprint)
                side = Side.REAR if Side.REAR in sides else next((s for s in sides if s is not Side.FRONT), None)
                if side and op.external_door(room, side, 2.4, DoorType.PATIO_SLIDING):
                    patio_room = room
                    break
        if patio_room is None:
            for room in sorted((b for b in boxes.values() if b.floor == 0 and b.type in (RoomType.UTILITY, RoomType.KITCHEN, RoomType.KITCHEN_DINING)), key=lambda b: b.type.value):
                sides = [s for s in exterior_sides(room.rect, op.footprint) if s is not Side.FRONT]
                if sides and op.external_door(room, sides[0], 0.9, DoorType.REAR):
                    break

        for room_id in self.intent.site.balcony_rooms:
            room = boxes.get(room_id)
            if room and room.floor > 0 and not op.balcony(room):
                self.notes.append(f"{room.name} has no exterior wall long enough for a balcony, so it was left out.")

        # Every room must be reachable from the front door through the house, not only from
        # the garden or the garage, so only the front door's room and the hall count as the way in.
        entrances = {ground.spine.id} | ({front_door.connects_room_a} if front_door else set())
        stranded = op.ensure_reachable(boxes, entrances)
        for room_id in stranded:
            self.notes.append(f"{boxes[room_id].name} could not be connected to the rest of the plan.")

        for box in boxes.values():
            op.glaze(box)
        return front_door, garage, patio_room

    # ------------------------------------------------------------------ assembly
    def _assemble(self, floors, stairs, op, front_door, garage, patio_room) -> BuildingSpecification:
        intent = self.intent
        rooms = [
            Room(id=b.id, name=b.name, type=b.type, floor=b.floor, x=b.rect.x, y=b.rect.y,
                 width=b.rect.width, depth=b.rect.depth)
            for zones in floors for b in sorted(zones.boxes(), key=lambda b: (b.rect.y, b.rect.x))
        ]
        ridge = Axis.X if self.width >= self.depth else Axis.Y
        roof = Roof(type=intent.roof.type, pitch=intent.roof.pitch, material=MaterialRef(id=intent.roof.material),
                    overhang=0.4 if intent.roof.type is RoofType.FLAT else 0.3,
                    ridge_direction=None if intent.roof.type is RoofType.FLAT else ridge)
        return BuildingSpecification(
            project=ProjectInfo(name=intent.project_name, description=intent.summary, style=intent.style),
            building=BuildingInfo(building_type=intent.building_type, width=self.width, depth=self.depth,
                                  floors=intent.floors, floor_height=intent.floor_height, slab_thickness=SLAB),
            floors=[Floor(level=i, name=_floor_name(i), elevation=round(i * intent.floor_height, 4), height=intent.floor_height)
                    for i in range(intent.floors)],
            rooms=rooms,
            doors=op.doors,
            windows=op.windows,
            stairs=[Stair(id=f"stair_{s.from_floor}", from_floor=s.from_floor, to_floor=s.from_floor + 1, x=s.x, y=s.y,
                          width=s.width, direction=StairDirection.FRONT_TO_REAR, risers=s.risers,
                          rise=round(s.rise, 5), run=s.run) for s in stairs],
            balconies=op.balconies,
            roof=roof,
            exterior=Exterior(
                wall_material=MaterialRef(id=intent.exterior.wall_material),
                accent_material=MaterialRef(id=intent.exterior.accent_material) if intent.exterior.accent_material else None,
                window_frame_material=MaterialRef(id=intent.exterior.window_frame_material),
                trim_material=MaterialRef(id=MaterialId.DARK_METAL),
            ),
            environment=plan_site(self.width, self.depth, front_door, garage, patio_room,
                                  intent.site.driveway, intent.site.patio),
        )

    def _area_notes(self, floors: list[FloorZones]) -> list[str]:
        notes = []
        for zones in floors:
            for box in zones.boxes():
                if box.synthetic or box.type in (RoomType.ENTRANCE, RoomType.HALLWAY, RoomType.LANDING):
                    continue
                change = (box.area - box.target_area) / box.target_area
                if abs(change) > AREA_NOTE_THRESHOLD:
                    notes.append(f"{box.name} is {box.area:.1f} m² ({'larger' if change > 0 else 'smaller'} than the "
                                 f"{box.target_area:.1f} m² requested) to fit the footprint.")
        return notes


def _row_min_depth(row: Row) -> float:
    """Depth a row needs in a column, whether or not its children end up beside it."""
    return min_depth(row.main) + sum(min_depth(c) for c in row.children) * 0.5


def _layout_cost(floors: list[FloorZones]) -> float:
    """Lower is better. Area drift is measured as a squared log ratio, so halving a room costs
    the same as doubling it, and weighted by the requested area so big rooms matter more.
    Rooms more than 2.5 times longer than wide are penalised as corridor-like."""
    cost = 0.0
    for zones in floors:
        for box in zones.boxes():
            if box is zones.spine or box.synthetic or box.rect is None or box.target_area <= 0:
                continue
            drift = math.log(max(box.area, 0.01) / box.target_area)
            aspect = max(box.rect.width, box.rect.depth) / max(min(box.rect.width, box.rect.depth), 0.01)
            cost += box.target_area * (drift * drift + 0.5 * max(0.0, aspect - 2.5) ** 2)
    return cost


def _floor_name(level: int) -> str:
    return ["Ground floor", "First floor", "Second floor", "Third floor"][level] if level < 4 else f"Floor {level}"


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


__all__ = ["PlanResult", "PlanningError", "plan_building"]
