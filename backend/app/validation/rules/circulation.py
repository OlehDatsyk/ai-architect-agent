"""Entrances, stairs and whether every room can actually be reached."""

from collections import deque
from collections.abc import Iterator

from app.geometry import stairs as stair_geo
from app.models.opening import PEDESTRIAN_ENTRANCE_TYPES, DoorType
from app.models.room import CIRCULATION_ROOMS, KITCHEN_CONNECTED_ROOMS, Room, RoomType
from app.models.stairs import Stair
from app.validation.context import ValidationContext, fmt
from app.validation.report import ValidationIssue, error, warning

EXTERIOR = "__exterior__"


def _ground_entrances(ctx: ValidationContext):
    return [d for d in ctx.spec.doors if d.is_external and d.floor == 0 and d.connects_room_a in ctx.rooms]


def check_entrance(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    pedestrian = [d for d in _ground_entrances(ctx) if d.type in PEDESTRIAN_ENTRANCE_TYPES]
    if not pedestrian:
        yield error("missing_entrance", "The building has no external door people can walk through on the ground floor.")
    elif not any(d.type is DoorType.FRONT for d in pedestrian):
        yield warning("missing_front_door", "The building has no front door; it is only entered from the rear or a patio door.")


def _stair_rooms(ctx: ValidationContext, stair: Stair) -> tuple[Room | None, Room | None]:
    start = ctx.rooms_containing(stair.from_floor, *stair_geo.stair_start_point(stair))
    arrival = ctx.rooms_containing(stair.to_floor, *stair_geo.stair_arrival_point(stair))
    return (start[0] if start else None), (arrival[0] if arrival else None)


def check_stairs(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for stair in ctx.spec.stairs:
        if stair.from_floor not in ctx.floors or stair.to_floor not in ctx.floors:
            yield error("stair_floor_missing", f"Stair {stair.id} connects floor {stair.from_floor} to floor {stair.to_floor}, but one of them does not exist.", stair.id)
            continue
        if stair.to_floor != stair.from_floor + 1:
            yield error("stair_floors_invalid", f"Stair {stair.id} must rise exactly one floor (got {stair.from_floor} to {stair.to_floor}).", stair.id)
            continue

        footprint = stair_geo.stair_footprint(stair)
        if not ctx.footprint.contains_rect(footprint):
            yield error("stair_outside_footprint", f"Stair {stair.id} extends outside the building.", stair.id)

        start_room, arrival_room = _stair_rooms(ctx, stair)
        if start_room is None:
            yield error("stair_start_not_in_room", f"Stair {stair.id} does not start inside a room on {ctx.floor_name(stair.from_floor)}.", stair.id)
        if arrival_room is None:
            yield error("stair_arrival_not_in_room", f"Stair {stair.id} does not arrive inside a room on {ctx.floor_name(stair.to_floor)}.", stair.id)

        for room in ctx.spec.rooms_on_floor(stair.to_floor):
            if room.type not in CIRCULATION_ROOMS and ctx.room_rect(room).intersection_area(footprint) > 0.05:
                yield warning("stair_rises_into_room", f"Stair {stair.id} rises through {room.name}; the stairwell should be in a landing or hallway.", stair.id, room.id)

        floor_to_floor = ctx.floors[stair.to_floor].elevation - ctx.floors[stair.from_floor].elevation
        if abs(stair.rise * stair.risers - floor_to_floor) > 0.005:
            yield error(
                "stair_height_mismatch",
                f"Stair {stair.id} climbs {fmt(stair.rise * stair.risers)} m but the floors are {fmt(floor_to_floor)} m apart.",
                stair.id,
            )
        yield from _stair_comfort(stair)


def _stair_comfort(stair: Stair) -> Iterator[ValidationIssue]:
    if stair.rise > stair_geo.MAX_RISE:
        yield warning("stair_steep_rise", f"Stair {stair.id} risers are {stair.rise * 1000:.0f} mm, above the typical {stair_geo.MAX_RISE * 1000:.0f} mm.", stair.id)
    elif stair.rise < stair_geo.MIN_RISE:
        yield warning("stair_shallow_rise", f"Stair {stair.id} risers are {stair.rise * 1000:.0f} mm, below the typical {stair_geo.MIN_RISE * 1000:.0f} mm.", stair.id)
    if stair.run < stair_geo.MIN_RUN:
        yield warning("stair_short_tread", f"Stair {stair.id} treads are {stair.run * 1000:.0f} mm deep, below the typical {stair_geo.MIN_RUN * 1000:.0f} mm.", stair.id)
    pitch = stair_geo.pitch_deg(stair.rise, stair.run)
    if pitch > stair_geo.MAX_PITCH_DEG:
        yield warning("stair_steep_pitch", f"Stair {stair.id} pitch is {pitch:.0f}°, steeper than the typical {stair_geo.MAX_PITCH_DEG:.0f}°.", stair.id)
    if stair.width < stair_geo.MIN_WIDTH:
        yield warning("stair_narrow", f"Stair {stair.id} is {fmt(stair.width)} m wide, narrower than the typical {fmt(stair_geo.MIN_WIDTH)} m.", stair.id)


def check_floors_connected(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    levels = sorted(ctx.floors)
    for lower, upper in zip(levels, levels[1:]):
        if not any(s.from_floor == lower and s.to_floor == upper for s in ctx.spec.stairs):
            yield error("floors_not_connected", f"No stair connects {ctx.floor_name(lower)} to {ctx.floor_name(upper)}.")


def check_rooms_reachable(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """Every room must be reachable from a ground-floor external door via doors and stairs."""
    if not _ground_entrances(ctx):
        return  # already reported as missing_entrance; avoid one error per room
    graph: dict[str, set[str]] = {EXTERIOR: set(), **{rid: set() for rid in ctx.rooms}}

    def link(a: str, b: str) -> None:
        graph[a].add(b)
        graph[b].add(a)

    for door in ctx.spec.doors:
        a, b = door.connects_room_a, door.connects_room_b
        if a not in ctx.rooms:
            continue
        if door.is_external and door.floor == 0:
            link(EXTERIOR, a)
        elif b in ctx.rooms:
            link(a, b)
    for stair in ctx.spec.stairs:
        start, arrival = _stair_rooms(ctx, stair)
        if start and arrival:
            link(start.id, arrival.id)

    seen, queue = {EXTERIOR}, deque([EXTERIOR])
    while queue:
        for neighbour in graph[queue.popleft()] - seen:
            seen.add(neighbour)
            queue.append(neighbour)
    for room in ctx.rooms.values():
        if room.id not in seen:
            yield error("room_inaccessible", f"{room.name} cannot be reached from an entrance.", room.id)


def check_kitchen_access(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """A separate kitchen should open onto a dining or living space when the building has one."""
    living_ids = {r.id for r in ctx.rooms.values() if r.type in KITCHEN_CONNECTED_ROOMS}
    if not living_ids:
        return
    for kitchen in (r for r in ctx.rooms.values() if r.type is RoomType.KITCHEN):
        neighbours = {
            d.connects_room_b if d.connects_room_a == kitchen.id else d.connects_room_a
            for d in ctx.spec.doors
            if kitchen.id in (d.connects_room_a, d.connects_room_b)
        }
        if not neighbours & living_ids:
            yield warning("kitchen_isolated", f"{kitchen.name} has no direct connection to a dining or living space.", kitchen.id)
