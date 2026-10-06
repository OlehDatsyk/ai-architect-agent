"""Identity, floors and overall building dimensions."""

from collections import Counter
from collections.abc import Iterator

from app.validation.context import ValidationContext, fmt
from app.validation.report import ValidationIssue, error, warning


def check_duplicate_ids(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    spec = ctx.spec
    ids = [
        *(r.id for r in spec.rooms), *(d.id for d in spec.doors), *(w.id for w in spec.windows),
        *(s.id for s in spec.stairs), *(b.id for b in spec.balconies),
    ]
    for element_id, count in Counter(ids).items():
        if count > 1:
            yield error("duplicate_id", f"ID '{element_id}' is used by {count} elements. Every element needs a unique ID.", element_id)


def check_floors(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    spec = ctx.spec
    levels = [f.level for f in spec.floors]
    if sorted(levels) != list(range(len(levels))):
        yield error("floor_levels_invalid", f"Floor levels must be numbered 0, 1, 2... with no gaps or repeats (got {sorted(levels)}).")
    if len(spec.floors) != spec.building.floors:
        yield error(
            "floor_count_mismatch",
            f"The building is described as {spec.building.floors} floor(s) but {len(spec.floors)} floor(s) are defined.",
        )
    for floor in spec.floors:
        if floor.height < 2.4:
            yield warning("floor_height_low", f"{floor.name} is only {fmt(floor.height)} m floor to floor, which is unusually low.")
        elif floor.height > 5.0:
            yield warning("floor_height_high", f"{floor.name} is {fmt(floor.height)} m floor to floor, which is unusually tall.")


def check_building_dimensions(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    b = ctx.spec.building
    for label, value in (("width", b.width), ("depth", b.depth)):
        if value < 4:
            yield warning("building_too_small", f"Building {label} of {fmt(value)} m is unrealistically small.")
        elif value > 80:
            yield warning("building_too_large", f"Building {label} of {fmt(value)} m is unusually large for this tool.")
