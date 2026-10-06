"""Places doors, windows and balconies on the walls the layout produced."""

from collections import deque

from app.geometry.rect import Rect, Segment, edge, exterior_sides, shared_segment
from app.models.common import Axis, Point2D, Side
from app.models.opening import Balcony, Door, DoorType, Window, WindowStyle
from app.models.room import CIRCULATION_ROOMS, RoomType
from app.planner.layout import PRECISION, place_in_free_space
from app.planner.model import Box, FloorZones, StairPlan
from app.planner.zoning import Zoning

DOOR_HEIGHT = 2.1
WET_ROOMS = frozenset({RoomType.BATHROOM, RoomType.ENSUITE, RoomType.WC, RoomType.UTILITY})
SMALL_DOOR_ROOMS = WET_ROOMS | {RoomType.STORAGE}
LIVING_ROOMS = frozenset({RoomType.OPEN_PLAN_LIVING, RoomType.KITCHEN_DINING, RoomType.LIVING_ROOM,
                          RoomType.DINING_ROOM, RoomType.KITCHEN})
CORNER = 0.25        # keep openings this far from room corners
GAP = 0.3            # minimum wall between two openings

_ROTATION = {Side.FRONT: 0, Side.REAR: 180, Side.LEFT: 90, Side.RIGHT: 270}
# Rooms nobody should have to walk through to reach another room.
DEAD_END_ROOMS = WET_ROOMS | {RoomType.STORAGE, RoomType.GARAGE}
# Lower rank = better room to walk through when a door has to be added for access.
_THROUGH_RANK = {**dict.fromkeys(CIRCULATION_ROOMS, 0), **dict.fromkeys(LIVING_ROOMS, 1),
                 RoomType.OFFICE: 2, RoomType.WORKSPACE: 2, RoomType.MEETING_ROOM: 2,
                 RoomType.UTILITY: 3, RoomType.BEDROOM: 4}


class OpeningPlanner:
    def __init__(self, zoning: Zoning, floors: list[FloorZones], stairs: list[StairPlan],
                 footprint: Rect, room_height: dict[int, float]) -> None:
        self.zoning = zoning
        self.floors = floors
        self.stairs = stairs
        self.footprint = footprint
        self.room_height = room_height
        self.notes: list[str] = []
        self.doors: list[Door] = []
        self.windows: list[Window] = []
        self.balconies: list[Balcony] = []
        self._ids: set[str] = set()
        self._used: dict[tuple, list[tuple[float, float]]] = {}
        self._connected: set[frozenset[str]] = set()
        self._block_stair_walls()

    # ------------------------------------------------------------------ bookkeeping
    def _line(self, level: int, segment: Segment) -> tuple:
        return (level, segment.axis, round(segment.coord, PRECISION))

    def _unique(self, base: str) -> str:
        candidate, n = base, 1
        while candidate in self._ids:
            n += 1
            candidate = f"{base}_{n}"
        self._ids.add(candidate)
        return candidate

    def _block_stair_walls(self) -> None:
        """Doors cannot open onto the side of a stair or its stairwell on the floor above."""
        spines = {f.level: f.spine for f in self.floors}
        for stair in self.stairs:
            if stair.side not in ("left", "right"):
                continue  # central stairs leave both spine walls free
            for level in (stair.from_floor, stair.from_floor + 1):
                spine = spines[level].rect
                wall_x = spine.x if stair.side == "left" else spine.x2
                key = (level, Axis.Y, round(wall_x, PRECISION))
                self._used.setdefault(key, []).append((stair.y - 0.1, stair.y + stair.length + 0.1))

    # ------------------------------------------------------------------ doors
    def connect(self, a: Box, b: Box, kind: str = "door") -> bool:
        if frozenset((a.id, b.id)) in self._connected:
            return True
        wall = shared_segment(a.rect, b.rect)
        if wall is None:
            return False
        if kind == "open":
            widest = min(max(wall.length - 0.6, 0.9), 2.4)
            widths = [w for w in (widest, 1.8, 1.2, 0.9) if w <= widest]
        else:
            widths = [0.8 if {a.type, b.type} & SMALL_DOOR_ROOMS else 0.9]
        used = self._used.setdefault(self._line(a.floor, wall), [])
        for width in widths:  # open-plan links take the widest opening that fits
            width = round(width, PRECISION)
            centre = place_in_free_space(wall.start, wall.end, width, used, margin=0.15)
            if centre is not None:
                break
        else:
            return False
        position = Point2D(x=centre, y=wall.coord) if wall.axis is Axis.X else Point2D(x=wall.coord, y=centre)
        self.doors.append(Door(
            id=self._unique(f"door_{a.id}_{b.id}"[:64]), type=DoorType.OPENING if kind == "open" else DoorType.INTERNAL,
            floor=a.floor, position=position, rotation=0 if wall.axis is Axis.X else 90, width=width,
            height=self._door_height(a.floor), connects_room_a=a.id, connects_room_b=b.id, is_external=False,
        ))
        used.append((centre - width / 2, centre + width / 2))
        self._connected.add(frozenset((a.id, b.id)))
        return True

    def _door_height(self, level: int) -> float:
        return round(min(DOOR_HEIGHT, self.room_height[level] - 0.1), PRECISION)

    def external_door(self, room: Box, side: Side, width: float, door_type: DoorType,
                      prefer: float | None = None, height: float | None = None) -> Door | None:
        wall = edge(room.rect, side)
        width = round(min(width, wall.length - 2 * CORNER), PRECISION)
        if width < 0.8:
            return None
        used = self._used.setdefault(self._line(room.floor, wall), [])
        centre = place_in_free_space(wall.start, wall.end, width, used, margin=CORNER, prefer=prefer)
        if centre is None:
            return None
        position = Point2D(x=centre, y=wall.coord) if wall.axis is Axis.X else Point2D(x=wall.coord, y=centre)
        door = Door(
            id=self._unique(f"door_{room.id}_{side.value}"[:64]), type=door_type, floor=room.floor,
            position=position, rotation=_ROTATION[side], width=width,
            height=height or self._door_height(room.floor), connects_room_a=room.id, is_external=True,
        )
        self.doors.append(door)
        used.append((centre - width / 2 - GAP / 2, centre + width / 2 + GAP / 2))
        return door

    # ------------------------------------------------------------------ windows
    def window(self, room: Box, side: Side, width: float, height: float, sill: float, style: WindowStyle) -> bool:
        wall = edge(room.rect, side)
        used = self._used.setdefault(self._line(room.floor, wall), [])
        ceiling = self.room_height[room.floor]
        height = round(min(height, ceiling - sill - 0.1), PRECISION)
        for attempt_width in (width, width * 0.75, width * 0.5):
            attempt_width = round(min(attempt_width, wall.length - 2 * CORNER), PRECISION)
            if attempt_width < 0.5 or height < 0.4:
                return False
            centre = place_in_free_space(wall.start, wall.end, attempt_width, used, margin=CORNER)
            if centre is not None:
                self.windows.append(Window(
                    id=self._unique(f"win_{room.id}_{side.value}"[:64]), style=style, room=room.id, wall=side,
                    offset=centre, width=attempt_width, height=height, sill_height=sill,
                ))
                used.append((centre - attempt_width / 2 - GAP / 2, centre + attempt_width / 2 + GAP / 2))
                return True
        return False

    def glaze(self, room: Box) -> None:
        sides = exterior_sides(room.rect, self.footprint)
        if not sides or room.glazing == "none" or room.type is RoomType.GARAGE:
            return
        ceiling = self.room_height[room.floor]
        preferred = [s for s in sides if s.value == room.preferred_side]
        ordered = preferred + sorted((s for s in sides if s not in preferred), key=lambda s: -edge(room.rect, s).length)

        if room.type in WET_ROOMS:
            self.window(room, ordered[0], 0.7, 0.8, min(1.3, ceiling - 0.9), WindowStyle.CASEMENT)
            return
        if room.type in CIRCULATION_ROOMS:
            for side in ordered:
                if self.window(room, side, 1.0, 1.2, 0.9, WindowStyle.FIXED):
                    return
            return

        count = 2 if room.glazing in ("large", "floor_to_ceiling") or room.area > 25 else 1
        placed = 0
        for side in ordered:
            wall_length = edge(room.rect, side).length
            if room.glazing == "floor_to_ceiling":
                ok = self.window(room, side, min(wall_length * 0.6, 3.0), ceiling - 0.3, 0.0, WindowStyle.FLOOR_TO_CEILING)
            elif room.glazing == "large":
                ok = self.window(room, side, min(wall_length * 0.5, 2.8), min(1.8, ceiling - 0.8), 0.6, WindowStyle.CASEMENT)
            else:
                ok = self.window(room, side, min(wall_length * 0.4, 1.6), min(1.3, ceiling - 1.0), 0.9, WindowStyle.CASEMENT)
            placed += ok
            if placed >= count:
                return

    # ------------------------------------------------------------------ balconies
    def balcony(self, room: Box) -> bool:
        sides = exterior_sides(room.rect, self.footprint)
        for side in sorted(sides, key=lambda s: [Side.REAR, Side.LEFT, Side.RIGHT, Side.FRONT].index(s)):
            wall = edge(room.rect, side)
            width = round(min(3.0, wall.length - 2 * CORNER), PRECISION)
            if width < 1.8:
                continue
            door = self.external_door(room, side, min(1.8, width - 0.4), DoorType.PATIO_SLIDING)
            if door is None:
                continue
            centre = door.position.x if wall.axis is Axis.X else door.position.y
            centre = round(min(max(centre, wall.start + width / 2), wall.end - width / 2), PRECISION)
            self.balconies.append(Balcony(id=self._unique(f"balcony_{room.id}"[:64]), room=room.id, wall=side,
                                          offset=centre, width=width, depth=1.5))
            return True
        return False

    # ------------------------------------------------------------------ access
    def ensure_reachable(self, boxes: dict[str, Box], entrances: set[str]) -> list[str]:
        """Add doors through neighbouring rooms until every room can be reached.
        Returns the IDs of rooms that still cannot be reached."""
        stair_links = {frozenset((f.spine.id, g.spine.id)) for f, g in zip(self.floors, self.floors[1:])}
        while True:
            links = self._connected | stair_links
            seen, queue = set(entrances), deque(entrances)
            while queue:
                current = queue.popleft()
                for pair in links:
                    if current in pair:
                        other = next(iter(pair - {current}), current)
                        if other not in seen:
                            seen.add(other)
                            queue.append(other)
            unreachable = [b for b in boxes.values() if b.id not in seen]
            if not unreachable:
                return []
            added = False
            # Main rooms first: once a bedroom has a door, its en-suite is reachable through it.
            for box in sorted(unreachable, key=lambda b: b.type in DEAD_END_ROOMS):
                options = [
                    other for other in boxes.values()
                    if other.id in seen and other.floor == box.floor and shared_segment(box.rect, other.rect)
                ]
                # Try circulation and living spaces first; a bathroom or store only as a last resort.
                ranked = sorted(options, key=lambda o: (o.type in DEAD_END_ROOMS, _THROUGH_RANK.get(o.type, 5)))
                for other in ranked:
                    if self.connect(other, box):
                        self.notes.append(f"Added a door between {other.name} and {box.name} so {box.name} can be reached.")
                        added = True
                        break
                if added:
                    break
            if not added:
                return [b.id for b in unreachable]
