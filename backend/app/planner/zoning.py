"""Decides what each room is (spine, rear slot, child or column room), which side of the
spine it goes on, and its order from front to rear."""

from collections import defaultdict

from app.models.intent import DesignIntent
from app.models.room import CIRCULATION_ROOMS, RoomType
from app.planner.model import Box, FloorZones, Row

SPINE_TYPES = frozenset({RoomType.ENTRANCE, RoomType.HALLWAY, RoomType.LANDING})
CHILD_TYPES = frozenset({RoomType.ENSUITE, RoomType.STORAGE, RoomType.WC})
SLOT_PRIORITY = {
    0: (RoomType.WC, RoomType.STORAGE, RoomType.UTILITY),
    1: (RoomType.BATHROOM, RoomType.STORAGE, RoomType.WC),
}
_ORDER = {"front": 1, "any": 2, "left": 2, "right": 2, "rear": 3}


class Zoning:
    """Holds rooms per floor and the (possibly re-pointed) connections between them."""

    def __init__(self, intent: DesignIntent) -> None:
        self.intent = intent
        self.notes: list[str] = []
        self.boxes: dict[str, Box] = {
            r.id: Box(r.id, r.name, r.type, r.floor, r.target_area, r.glazing, r.preferred_side) for r in intent.rooms
        }
        self.links: dict[frozenset[str], str] = {}  # {a, b} -> "door" | "open"
        for c in intent.connections:
            if c.room_a != c.room_b:
                self.links[frozenset((c.room_a, c.room_b))] = c.kind
        self.spines: dict[int, Box] = {}

    # ------------------------------------------------------------------ helpers
    def neighbours(self, room_id: str) -> set[str]:
        return {other for pair in self.links for other in pair if room_id in pair and other != room_id}

    def link(self, a: str, b: str) -> str | None:
        return self.links.get(frozenset((a, b)))

    def _unique_id(self, base: str) -> str:
        candidate, n = base, 1
        while candidate in self.boxes:
            n += 1
            candidate = f"{base}_{n}"
        return candidate

    def _repoint(self, old: str, new: str) -> None:
        for pair, kind in list(self.links.items()):
            if old in pair:
                del self.links[pair]
                others = [r for r in pair if r != old] or [new]
                if others[0] != new:
                    self.links[frozenset((new, others[0]))] = kind

    # ------------------------------------------------------------------ spine
    def choose_spines(self) -> None:
        """One circulation room per floor runs front to rear and holds the stairs."""
        intent = self.intent
        for level in range(intent.floors):
            candidate: Box | None = None
            if level == 0:
                entrance = self.boxes.get(intent.entrance_room)
                if entrance and entrance.type in SPINE_TYPES:
                    candidate = entrance
            else:
                arrivals = [s.arrival_room for s in intent.stairs if s.to_floor == level]
                candidate = next((self.boxes[r] for r in arrivals if r in self.boxes and self.boxes[r].type in SPINE_TYPES), None)
            if candidate is None:
                candidate = next((b for b in self.floor_boxes(level) if b.type in SPINE_TYPES), None)
            if candidate is None:
                kind = RoomType.ENTRANCE if level == 0 else RoomType.LANDING
                name = "Entrance Hall" if level == 0 else "Landing"
                candidate = Box(self._unique_id("hall" if level == 0 else "landing"), name, kind, level, 8.0, synthetic=True)
                self.boxes[candidate.id] = candidate
                self.notes.append(f"Added {name.lower()} on {floor_label(level)} to hold the stairs and give access to every room.")
                if level == 0 and intent.entrance_room in self.boxes:
                    self.links[frozenset((candidate.id, intent.entrance_room))] = "door"
            self.spines[level] = candidate

            # Other halls and corridors on the same floor are absorbed into the spine.
            for extra in [b for b in self.floor_boxes(level) if b.type in SPINE_TYPES and b is not candidate]:
                candidate.target_area += extra.target_area
                self._repoint(extra.id, candidate.id)
                del self.boxes[extra.id]
                self.notes.append(f"Merged {extra.name} into {candidate.name}; the plan uses one circulation space per floor.")

    def floor_boxes(self, level: int) -> list[Box]:
        return [b for b in self.boxes.values() if b.floor == level]

    # ------------------------------------------------------------------ per floor
    def parent_of(self, box: Box) -> str | None:
        """A small room reached only through one other (non-circulation) room hangs off it."""
        if box.type not in CHILD_TYPES:
            return None
        neighbours = self.neighbours(box.id)
        if len(neighbours) != 1:
            return None
        parent = self.boxes.get(next(iter(neighbours)))
        if parent is None or parent.floor != box.floor or parent.type in CIRCULATION_ROOMS or parent.type in CHILD_TYPES:
            return None
        return parent.id

    def zone_floor(self, level: int) -> tuple[FloorZones, list[Row]]:
        spine = self.spines[level]
        zones = FloorZones(level=level, spine=spine)
        others = [b for b in self.floor_boxes(level) if b is not spine]

        children: dict[str, list[Box]] = defaultdict(list)
        for box in others:
            parent = self.parent_of(box)
            if parent:
                children[parent].append(box)
        child_ids = {c.id for group in children.values() for c in group}

        candidates = [b for b in others if b.id not in child_ids and b.id not in children]
        for wanted in SLOT_PRIORITY[min(level, 1)]:
            slot = next((b for b in sorted(candidates, key=lambda b: b.target_area) if b.type is wanted), None)
            if slot is not None:
                zones.slot = slot
                break

        rows = [Row(b, children.get(b.id, [])) for b in others if b.id not in child_ids and b is not zones.slot]
        return zones, rows


def floor_label(level: int) -> str:
    return ["the ground floor", "the first floor", "the second floor"][level] if level < 3 else f"floor {level}"


def group_rows(rows: list[Row], zoning: Zoning) -> list[list[Row]]:
    """Rows joined by an open-plan link stay on the same side of the spine."""
    parent = {id(r): id(r) for r in rows}
    by_room = {r.main.id: r for r in rows}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for pair, kind in zoning.links.items():
        a, b = tuple(pair)
        if kind == "open" and a in by_room and b in by_room:
            parent[find(id(by_room[a]))] = find(id(by_room[b]))
    groups: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        groups[find(id(r))].append(r)
    return list(groups.values())


def assign_sides(rows: list[Row], zoning: Zoning, capacity: tuple[float, float],
                 depth: float = float("inf"), min_depth=lambda row: 0.0,
                 fixed: dict[str, int] | None = None) -> tuple[list[Row], list[Row]]:
    """Split rows between the left and right columns, balancing area against each column's
    capacity while making sure each column can hold its rooms' minimum depths.

    `fixed` keeps rooms on the side they were on in an earlier plan (when a design is modified);
    an explicit left or right preference still wins."""
    left: list[Row] = []
    right: list[Row] = []
    load = [0.0, 0.0]
    stacked = [0.0, 0.0]
    for group in sorted(group_rows(rows, zoning), key=lambda g: -sum(r.area for r in g)):
        prefs = {r.main.preferred_side for r in group} & {"left", "right"}
        if prefs == {"left"}:
            side = 0
        elif prefs == {"right"}:
            side = 1
        elif fixed and any(r.main.id in fixed for r in group):
            known = [fixed[r.main.id] for r in group if r.main.id in fixed]
            side = round(sum(known) / len(known))
        else:
            fill = [load[i] / capacity[i] if capacity[i] > 0 else float("inf") for i in (0, 1)]
            side = 0 if fill[0] <= fill[1] else 1
            needed = sum(min_depth(r) for r in group)
            if stacked[side] + needed > depth and stacked[1 - side] + needed <= depth and capacity[1 - side] > 0:
                side = 1 - side
        (left if side == 0 else right).extend(group)
        load[side] += sum(r.area for r in group)
        stacked[side] += sum(min_depth(r) for r in group)
    return left, right


def order_rows(rows: list[Row], zoning: Zoning, positions: dict[str, float] | None = None) -> list[Row]:
    """Front to rear: garages first, then rooms that want the front, then the rest, garden rooms last.
    Connected rooms are kept next to each other where possible.

    With `positions` (from an earlier plan), rooms keep their earlier order and new rooms go behind them."""
    if positions:
        known = sorted((r for r in rows if r.main.id in positions), key=lambda r: positions[r.main.id])
        return known + order_rows([r for r in rows if r.main.id not in positions], zoning)
    def key(r: Row) -> tuple[int, float]:
        rank = 0 if r.main.type is RoomType.GARAGE else _ORDER.get(r.main.preferred_side, 2)
        # Among garden-facing rooms the largest goes rearmost; elsewhere larger rooms come first.
        return rank, r.area if rank == _ORDER["rear"] else -r.area

    ordered = sorted(rows, key=key)
    for i in range(len(ordered) - 2):
        if zoning.link(ordered[i].main.id, ordered[i + 1].main.id):
            continue
        for j in range(i + 2, len(ordered)):
            if key(ordered[j])[0] == key(ordered[i + 1])[0] and zoning.link(ordered[i].main.id, ordered[j].main.id):
                ordered[i + 1], ordered[j] = ordered[j], ordered[i + 1]
                break
    return ordered
