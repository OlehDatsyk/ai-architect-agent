"""Room placement, size, height and support."""

from collections.abc import Iterator
from itertools import combinations

from app.models.materials import MATERIAL_USES, MaterialUse
from app.models.room import RoomType
from app.validation.context import ValidationContext, fmt
from app.validation.report import ValidationIssue, error, warning

OVERLAP_TOLERANCE_M2 = 0.01
MIN_SIDE = 0.6
MIN_CLEAR_HEIGHT = 2.1
UNSUPPORTED_TOLERANCE_M2 = 0.5

# Typical minimum areas (m²). Smaller rooms get a warning, not an error.
TYPICAL_MIN_AREA: dict[RoomType, float] = {
    RoomType.BEDROOM: 6.5, RoomType.BATHROOM: 3.5, RoomType.ENSUITE: 2.5, RoomType.WC: 1.2,
    RoomType.KITCHEN: 5.0, RoomType.LIVING_ROOM: 11.0, RoomType.DINING_ROOM: 7.0,
    RoomType.KITCHEN_DINING: 12.0, RoomType.OPEN_PLAN_LIVING: 20.0, RoomType.OFFICE: 5.0,
    RoomType.GARAGE: 13.0, RoomType.MEETING_ROOM: 8.0, RoomType.UTILITY: 2.5,
}

_SIDE_WORDS = {"left": "left", "right": "right", "front": "front", "rear": "rear"}


def check_room_floors(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for room in ctx.spec.rooms:
        if room.floor not in ctx.floors:
            yield error("room_floor_missing", f"{room.name} is on floor {room.floor}, which does not exist.", room.id)


def check_rooms_inside_footprint(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for room in ctx.spec.rooms:
        overhang = ctx.room_rect(room).overhang(ctx.footprint)
        if overhang:
            parts = ", ".join(f"{fmt(v)} m beyond the {_SIDE_WORDS[s.value]} wall" for s, v in overhang.items())
            yield error("room_outside_footprint", f"{room.name} extends {parts}.", room.id)


def check_room_overlaps(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for a, b in combinations(ctx.spec.rooms, 2):
        if a.floor != b.floor:
            continue
        area = ctx.room_rect(a).intersection_area(ctx.room_rect(b))
        if area > OVERLAP_TOLERANCE_M2:
            yield error("room_overlap", f"{a.name} overlaps {b.name} by {fmt(area)} m².", a.id, b.id)


def check_room_sizes(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for room in ctx.spec.rooms:
        shortest = min(room.width, room.depth)
        if shortest < MIN_SIDE:
            yield error("room_too_narrow", f"{room.name} is only {fmt(shortest)} m across, too narrow to use.", room.id)
            continue
        minimum = TYPICAL_MIN_AREA.get(room.type)
        if minimum and room.area < minimum:
            yield warning(
                "room_small",
                f"{room.name} is {fmt(room.area)} m², below the typical minimum of {fmt(minimum)} m² for a {room.type.value.replace('_', ' ')}.",
                room.id,
            )


def check_room_heights(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    slab = ctx.spec.building.slab_thickness
    for room in ctx.spec.rooms:
        floor = ctx.floors.get(room.floor)
        height = ctx.room_height(room)
        if floor is None or height is None:
            continue
        available = floor.height - slab
        if height > available + 0.005:
            yield error(
                "room_height_exceeds_floor",
                f"{room.name} is {fmt(height)} m high but {floor.name} only allows {fmt(available)} m below the next slab.",
                room.id,
            )
        elif height < MIN_CLEAR_HEIGHT:
            yield warning("room_height_low", f"{room.name} has only {fmt(height)} m clear height.", room.id)


def check_upper_floor_support(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """Upper-floor rooms should sit over rooms on the floor below, not over open ground."""
    for room in ctx.spec.rooms:
        if room.floor == 0 or room.floor - 1 not in ctx.floors:
            continue
        rect = ctx.room_rect(room)
        supported = sum(rect.intersection_area(ctx.room_rect(r)) for r in ctx.spec.rooms_on_floor(room.floor - 1))
        unsupported = rect.area - supported
        if unsupported > UNSUPPORTED_TOLERANCE_M2:
            yield warning(
                "room_unsupported",
                f"{room.name} on {ctx.floor_name(room.floor)} sits over {fmt(unsupported)} m² with no room below it.",
                room.id,
            )


def check_materials(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    def unsuitable(material_id, use: MaterialUse) -> bool:
        return use not in MATERIAL_USES[material_id]

    for room in ctx.spec.rooms:
        for label, ref in (("walls", room.wall_material), ("floor", room.floor_material), ("ceiling", room.ceiling_material)):
            if ref is not None and unsuitable(ref.id, MaterialUse.INTERIOR):
                yield warning("material_unusual", f"{room.name} {label} use '{ref.id.value}', which is not an interior finish.", room.id)
    ext = ctx.spec.exterior
    for label, ref in (("exterior walls", ext.wall_material), ("exterior accent", ext.accent_material)):
        if ref is not None and unsuitable(ref.id, MaterialUse.EXTERIOR_WALL):
            yield warning("material_unusual", f"The {label} use '{ref.id.value}', which is not an exterior wall material.")
    if unsuitable(ctx.spec.roof.material.id, MaterialUse.ROOF):
        yield warning("material_unusual", f"The roof uses '{ctx.spec.roof.material.id.value}', which is not a roofing material.")
