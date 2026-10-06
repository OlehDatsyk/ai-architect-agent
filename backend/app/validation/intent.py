"""Deterministic checks on Claude's DesignIntent, and enforcement of the user's advanced controls.

Valid JSON is not the same as a sensible building, so every interpretation passes through
these checks. Errors are fed back to Claude for one corrective attempt; warnings are shown
to the user on the review screen.
"""

from collections import Counter, deque
from collections.abc import Iterator

from app.models.intent import DesignConstraints, DesignIntent
from app.models.roof import RoofType
from app.models.room import CIRCULATION_ROOMS, HABITABLE_ROOMS, KITCHEN_CONNECTED_ROOMS, RoomType
from app.validation.report import ValidationIssue, ValidationReport, error, warning
from app.validation.rules.rooms import TYPICAL_MIN_AREA

# Every floor fills the same rectangular footprint, so room areas per floor should add up
# to roughly the footprint area. The planner scales rooms to fit within these bounds.
MAX_FILL = 1.10
MIN_FILL = 0.70
DOUBLE_GARAGE_AREA = 28.0


def apply_constraints(intent: DesignIntent, constraints: DesignConstraints) -> tuple[DesignIntent, list[str]]:
    """Apply advanced controls that can be enforced directly. Returns the updated intent and
    a plain-English note for each change. Count-type controls (bedrooms, floors...) can't be
    changed without redesigning, so they are checked by check_constraints instead."""
    updated = intent.model_copy(deep=True)
    notes: list[str] = []

    def set_field(obj, field: str, value, label: str) -> None:
        if value is not None and getattr(obj, field) != value:
            notes.append(f"{label} set to {value} as requested (Claude proposed {getattr(obj, field)}).")
            setattr(obj, field, value)

    c = constraints
    set_field(updated, "building_type", c.building_type, "Building type")
    set_field(updated, "style", c.style, "Style")
    set_field(updated, "footprint_width", c.width, "Width")
    set_field(updated, "footprint_depth", c.depth, "Depth")
    if c.roof != "automatic":
        roof_type = RoofType(c.roof)
        set_field(updated.roof, "type", roof_type, "Roof type")
        if roof_type is RoofType.FLAT and updated.roof.pitch > 3:
            updated.roof.pitch = 2.0
        elif roof_type is not RoofType.FLAT and updated.roof.pitch < 15:
            updated.roof.pitch = 10.0 if roof_type is RoofType.SHED else 35.0
    return updated, notes


def garage_size(intent: DesignIntent) -> str:
    garages = [r for r in intent.rooms if r.type is RoomType.GARAGE]
    if not garages:
        return "none"
    return "double" if max(g.target_area for g in garages) >= DOUBLE_GARAGE_AREA else "single"


def check_constraints(intent: DesignIntent, c: DesignConstraints) -> Iterator[ValidationIssue]:
    counts = Counter(r.type for r in intent.rooms)
    bathrooms = counts[RoomType.BATHROOM] + counts[RoomType.ENSUITE]
    checks = [
        ("floors", c.floors, intent.floors),
        ("bedrooms", c.bedrooms, counts[RoomType.BEDROOM]),
        ("bathrooms (including en-suites)", c.bathrooms, bathrooms),
        ("garage", c.garage, garage_size(intent)),
    ]
    for label, wanted, actual in checks:
        if wanted is not None and wanted != actual:
            yield error("constraint_not_met", f"The user requires {label} = {wanted}, but the design has {actual}.")
    if c.height is not None:
        walls = intent.floors * intent.floor_height
        if walls > c.height + 0.5:
            yield error("constraint_not_met", f"The user requires a height of about {c.height} m, but the walls alone are {walls:.1f} m tall.")


def check_intent(intent: DesignIntent) -> Iterator[ValidationIssue]:
    rooms = {r.id: r for r in intent.rooms}
    for room_id, n in Counter(r.id for r in intent.rooms).items():
        if n > 1:
            yield error("duplicate_id", f"Room ID '{room_id}' is used {n} times.", room_id)

    for room in intent.rooms:
        if room.floor >= intent.floors:
            yield error("room_floor_missing", f"{room.name} is on floor {room.floor}, but the building has {intent.floors} floor(s).", room.id)
        if room.type is RoomType.GARAGE and room.floor != 0:
            yield error("garage_not_on_ground", f"{room.name} must be on the ground floor.", room.id)
        minimum = TYPICAL_MIN_AREA.get(room.type)
        if minimum and room.target_area < minimum:
            yield warning("room_small", f"{room.name} is planned at {room.target_area:.1f} m², below the typical {minimum:.1f} m².", room.id)
        if room.type in HABITABLE_ROOMS and room.glazing == "none":
            yield warning("room_without_window", f"{room.name} is planned with no windows.", room.id)

    footprint = intent.footprint_width * intent.footprint_depth
    for level in range(intent.floors):
        on_floor = intent.rooms_on_floor(level)
        if not on_floor:
            yield error("floor_empty", f"Floor {level} has no rooms.")
            continue
        total = sum(r.target_area for r in on_floor)
        if total > footprint * MAX_FILL:
            yield error(
                "floor_area_exceeds_footprint",
                f"Rooms on floor {level} need {total:.0f} m², but the {intent.footprint_width:g} x {intent.footprint_depth:g} m footprint is only {footprint:.0f} m².",
            )
        elif total < footprint * MIN_FILL:
            yield warning("floor_underfilled", f"Rooms on floor {level} total {total:.0f} m² of a {footprint:.0f} m² footprint; they will be enlarged to fill it.")

    entrance = rooms.get(intent.entrance_room)
    if entrance is None:
        yield error("entrance_missing", f"The entrance room '{intent.entrance_room}' does not exist.")
    elif entrance.floor != 0:
        yield error("entrance_missing", f"The entrance room {entrance.name} must be on the ground floor.")

    yield from _check_connections(intent, rooms)
    yield from _check_stairs(intent, rooms)
    yield from _check_reachability(intent, rooms)

    for room_id in intent.site.balcony_rooms:
        room = rooms.get(room_id)
        if room is None or room.floor == 0:
            yield error("balcony_invalid", f"Balcony room '{room_id}' must be an existing upper-floor room.")

    if intent.roof.type is RoofType.FLAT and intent.roof.pitch > 5:
        yield error("roof_pitch_invalid", f"A flat roof cannot have a {intent.roof.pitch:g}° pitch.")
    if intent.roof.type is not RoofType.FLAT and not 5 <= intent.roof.pitch <= 70:
        yield error("roof_pitch_invalid", f"A {intent.roof.type.value} roof needs a pitch between 5° and 70°.")


def _check_connections(intent: DesignIntent, rooms: dict) -> Iterator[ValidationIssue]:
    for c in intent.connections:
        a, b = rooms.get(c.room_a), rooms.get(c.room_b)
        missing = [rid for rid, r in ((c.room_a, a), (c.room_b, b)) if r is None]
        if missing:
            yield error("connection_room_missing", f"A connection refers to room '{missing[0]}', which does not exist.")
            continue
        if c.room_a == c.room_b:
            yield error("connection_invalid", f"{a.name} is connected to itself.", a.id)
        elif a.floor != b.floor:
            yield error("connection_invalid", f"{a.name} and {b.name} are on different floors; floors are linked by stairs, not doors.", a.id, b.id)

    living = {r.id for r in intent.rooms if r.type in KITCHEN_CONNECTED_ROOMS}
    for kitchen in (r for r in intent.rooms if r.type is RoomType.KITCHEN):
        neighbours = {c.room_b if c.room_a == kitchen.id else c.room_a for c in intent.connections if kitchen.id in (c.room_a, c.room_b)}
        if living and not neighbours & living:
            yield warning("kitchen_isolated", f"{kitchen.name} is not connected to a dining or living space.", kitchen.id)


def _check_stairs(intent: DesignIntent, rooms: dict) -> Iterator[ValidationIssue]:
    for lower in range(intent.floors - 1):
        if not any(s.from_floor == lower and s.to_floor == lower + 1 for s in intent.stairs):
            yield error("floors_not_connected", f"No stair connects floor {lower} to floor {lower + 1}.")
    for s in intent.stairs:
        if s.to_floor != s.from_floor + 1:
            yield error("stair_floors_invalid", f"A stair must rise exactly one floor (got {s.from_floor} to {s.to_floor}).")
            continue
        for room_id, level, role in ((s.start_room, s.from_floor, "start"), (s.arrival_room, s.to_floor, "arrival")):
            room = rooms.get(room_id)
            if room is None or room.floor != level:
                yield error("stair_room_invalid", f"The stair {role} room '{room_id}' must exist on floor {level}.")
            elif room.type not in CIRCULATION_ROOMS:
                yield warning("stair_in_room", f"The stair {'starts in' if role == 'start' else 'arrives in'} {room.name}; a hall or landing is usual.", room.id)


def _check_reachability(intent: DesignIntent, rooms: dict) -> Iterator[ValidationIssue]:
    if intent.entrance_room not in rooms:
        return
    graph: dict[str, set[str]] = {rid: set() for rid in rooms}
    edges = [(c.room_a, c.room_b) for c in intent.connections] + [(s.start_room, s.arrival_room) for s in intent.stairs]
    for a, b in edges:
        if a in graph and b in graph:
            graph[a].add(b)
            graph[b].add(a)
    seen, queue = {intent.entrance_room}, deque([intent.entrance_room])
    while queue:
        for n in graph[queue.popleft()] - seen:
            seen.add(n)
            queue.append(n)
    for room in intent.rooms:
        if room.id not in seen:
            yield error("room_inaccessible", f"{room.name} cannot be reached from the entrance.", room.id)


def validate_intent(intent: DesignIntent, constraints: DesignConstraints) -> ValidationReport:
    issues = [*check_intent(intent), *check_constraints(intent, constraints)]
    return ValidationReport.build(issues, [])
