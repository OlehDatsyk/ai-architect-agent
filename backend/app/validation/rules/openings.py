"""Doors, windows and balconies: references, placement on real walls, heights and clashes."""

from collections.abc import Iterator
from itertools import combinations

from app.geometry.placement import balcony_segment, door_segment, exterior_side_of, window_segment
from app.geometry.rect import Segment, edge, exterior_sides, shared_segment, span_overlap
from app.models.common import Side
from app.models.opening import EXTERNAL_DOOR_TYPES, DoorType
from app.models.room import HABITABLE_ROOMS, Room, RoomType
from app.validation.context import ValidationContext, fmt
from app.validation.report import ValidationIssue, error, warning


def check_door_references(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for door in ctx.spec.doors:
        a = ctx.rooms.get(door.connects_room_a)
        b = ctx.rooms.get(door.connects_room_b) if door.connects_room_b else None
        if a is None:
            yield error("door_room_missing", f"Door {door.id} connects to room '{door.connects_room_a}', which does not exist.", door.id)
        if door.connects_room_b and b is None:
            yield error("door_room_missing", f"Door {door.id} connects to room '{door.connects_room_b}', which does not exist.", door.id)
        if door.is_external and door.connects_room_b is not None:
            yield error("door_connection_invalid", f"External door {door.id} should connect one room to the outside, not two rooms.", door.id)
        if not door.is_external and door.connects_room_b is None:
            yield error("door_connection_invalid", f"Internal door {door.id} must connect two rooms.", door.id)
        if door.connects_room_a == door.connects_room_b:
            yield error("door_connection_invalid", f"Door {door.id} connects a room to itself.", door.id)
        for room in (r for r in (a, b) if r is not None):
            if room.floor != door.floor:
                yield error("door_floor_mismatch", f"Door {door.id} is on floor {door.floor} but {room.name} is on floor {room.floor}.", door.id)
        if door.type in EXTERNAL_DOOR_TYPES and not door.is_external:
            yield warning("door_type_mismatch", f"Door {door.id} is a {door.type.value.replace('_', ' ')} door but is marked internal.", door.id)
        if door.is_external and door.type in (DoorType.INTERNAL, DoorType.OPENING):
            yield warning("door_type_mismatch", f"External door {door.id} has type '{door.type.value}'.", door.id)
        if door.type is DoorType.GARAGE and a is not None and a.type is not RoomType.GARAGE:
            yield warning("door_type_mismatch", f"Garage door {door.id} opens into {a.name}, which is not a garage.", door.id)


def check_door_placement(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for door in ctx.spec.doors:
        a = ctx.rooms.get(door.connects_room_a)
        if a is None:
            continue
        span = door_segment(door)
        if door.is_external:
            on_wall = any(
                _fits(edge(ctx.room_rect(a), side), span)
                for side in _sides_on_perimeter(ctx, a)
            )
            if not on_wall:
                yield error("door_not_on_exterior_wall", f"External door {door.id} is not on an exterior wall of {a.name}.", door.id)
            continue
        b = ctx.rooms.get(door.connects_room_b or "")
        if b is None:
            continue
        shared = shared_segment(ctx.room_rect(a), ctx.room_rect(b))
        if shared is None:
            yield error("door_rooms_not_adjacent", f"Door {door.id} connects {a.name} and {b.name}, which do not share a wall.", door.id)
        elif not _fits(shared, span):
            yield error(
                "door_not_on_shared_wall",
                f"Door {door.id} does not sit on the {fmt(shared.length)} m wall shared by {a.name} and {b.name}.",
                door.id,
            )


def check_door_heights(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for door in ctx.spec.doors:
        rooms = [r for r in (ctx.rooms.get(door.connects_room_a), ctx.rooms.get(door.connects_room_b or "")) if r]
        heights = [h for h in (ctx.room_height(r) for r in rooms) if h is not None]
        if heights and door.height > min(heights) + 0.005:
            yield error("door_too_tall", f"Door {door.id} is {fmt(door.height)} m high but the room is only {fmt(min(heights))} m high.", door.id)


def check_upper_floor_external_doors(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """An external door above ground floor must open onto a balcony."""
    for door in ctx.spec.doors:
        if not door.is_external or door.floor == 0:
            continue
        span = door_segment(door)
        side = exterior_side_of(span, ctx.footprint)
        has_balcony = any(
            b.wall == side
            and (room := ctx.rooms.get(b.room)) is not None and room.floor == door.floor
            and balcony_segment(b, ctx.footprint).contains_span(span.start, span.end)
            for b in ctx.spec.balconies
        )
        if not has_balcony:
            yield error("door_opens_onto_drop", f"External door {door.id} on {ctx.floor_name(door.floor)} does not open onto a balcony.", door.id)


def check_windows(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for window in ctx.spec.windows:
        room = ctx.rooms.get(window.room)
        if room is None:
            yield error("window_room_missing", f"Window {window.id} belongs to room '{window.room}', which does not exist.", window.id)
            continue
        if window.wall not in _sides_on_perimeter(ctx, room):
            yield error("window_not_on_exterior_wall", f"Window {window.id}: {room.name} does not touch the {window.wall.value} exterior wall.", window.id)
        elif not _fits(edge(ctx.room_rect(room), window.wall), window_segment(window, ctx.footprint)):
            yield error("window_outside_room_wall", f"Window {window.id} extends beyond {room.name}'s {window.wall.value} wall.", window.id)
        height = ctx.room_height(room)
        if height is not None and window.sill_height + window.height > height + 0.005:
            yield error(
                "window_too_tall",
                f"Window {window.id} reaches {fmt(window.sill_height + window.height)} m, above {room.name}'s {fmt(height)} m ceiling.",
                window.id,
            )


def check_exterior_opening_clashes(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """Windows and external doors on the same wall of the same floor must not overlap."""
    openings: list[tuple[str, int, Segment]] = []
    for window in ctx.spec.windows:
        room = ctx.rooms.get(window.room)
        if room is not None:
            openings.append((window.id, room.floor, window_segment(window, ctx.footprint)))
    for door in ctx.spec.doors:
        if door.is_external:
            openings.append((door.id, door.floor, door_segment(door)))
    for (id_a, floor_a, seg_a), (id_b, floor_b, seg_b) in combinations(openings, 2):
        if floor_a == floor_b and seg_a.is_on_line(seg_b.axis, seg_b.coord):
            overlap = span_overlap(seg_a.start, seg_a.end, seg_b.start, seg_b.end)
            if overlap > 0.01:
                yield error("openings_overlap", f"{id_a} and {id_b} overlap by {fmt(overlap)} m on the same wall.", id_a, id_b)


def check_habitable_rooms_have_windows(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    with_windows = {w.room for w in ctx.spec.windows}
    glazed_doors = {d.connects_room_a for d in ctx.spec.doors if d.type is DoorType.PATIO_SLIDING}
    for room in ctx.spec.rooms:
        if room.type in HABITABLE_ROOMS and room.id not in with_windows | glazed_doors:
            yield warning("room_without_window", f"{room.name} has no exterior window.", room.id)


def check_balconies(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for balcony in ctx.spec.balconies:
        room = ctx.rooms.get(balcony.room)
        if room is None:
            yield error("balcony_room_missing", f"Balcony {balcony.id} belongs to room '{balcony.room}', which does not exist.", balcony.id)
            continue
        if room.floor == 0:
            yield warning("balcony_on_ground_floor", f"Balcony {balcony.id} is on the ground floor; a patio may be intended.", balcony.id)
        if balcony.wall not in _sides_on_perimeter(ctx, room):
            yield error("balcony_not_on_exterior_wall", f"Balcony {balcony.id}: {room.name} does not touch the {balcony.wall.value} exterior wall.", balcony.id)
            continue
        if not _fits(edge(ctx.room_rect(room), balcony.wall), balcony_segment(balcony, ctx.footprint)):
            yield error("balcony_outside_room_wall", f"Balcony {balcony.id} is wider than {room.name}'s {balcony.wall.value} wall.", balcony.id)
        has_access = any(
            d.is_external and d.connects_room_a == room.id
            and exterior_side_of(door_segment(d), ctx.footprint) == balcony.wall
            for d in ctx.spec.doors
        )
        if not has_access:
            yield warning("balcony_without_door", f"Balcony {balcony.id} has no door from {room.name}.", balcony.id)


def _sides_on_perimeter(ctx: ValidationContext, room: Room) -> list[Side]:
    return exterior_sides(ctx.room_rect(room), ctx.footprint)


def _fits(wall: Segment, opening: Segment) -> bool:
    return opening.is_on_line(wall.axis, wall.coord) and wall.contains_span(opening.start, opening.end)
