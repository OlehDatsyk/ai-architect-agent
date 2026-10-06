"""Safe, obvious corrections applied before validation. Every correction is reported.

Anything that changes a design decision (moving a room, changing room sizes by more than
a rounding error, choosing a different roof) is never done here; it is reported instead.
"""

from app.geometry.rect import Rect
from app.geometry.roof import ridge_axis
from app.geometry.stairs import MAX_RISE, MIN_RISE
from app.models.building import BuildingSpecification
from app.models.opening import WindowStyle
from app.models.roof import RoofType
from app.validation.context import fmt
from app.validation.report import AppliedFix

# A room overshooting the footprint by up to this much is snapped back inside.
SNAP_LIMIT = 0.05
ELEVATION_TOLERANCE = 0.005


def apply_fixes(spec: BuildingSpecification) -> tuple[BuildingSpecification, list[AppliedFix]]:
    fixed = spec.model_copy(deep=True)
    fixes: list[AppliedFix] = []

    fixed.floors.sort(key=lambda f: f.level)
    _fix_floor_elevations(fixed, fixes)
    _fill_room_heights(fixed)
    _snap_rooms_to_footprint(fixed, fixes)
    _fix_stair_rise(fixed, fixes)
    _default_ridge_direction(fixed, fixes)
    _floor_to_ceiling_sills(fixed, fixes)
    return fixed, fixes


def _fix_floor_elevations(spec: BuildingSpecification, fixes: list[AppliedFix]) -> None:
    levels = [f.level for f in spec.floors]
    if levels != list(range(len(levels))):
        return  # invalid floor numbering is an error, reported by a rule
    elevation = 0.0
    for floor in spec.floors:
        if abs(floor.elevation - elevation) > ELEVATION_TOLERANCE:
            fixes.append(AppliedFix(
                code="floor_elevation_corrected",
                message=f"Set {floor.name} elevation to {fmt(elevation)} m to match the floor heights below it "
                        f"(was {fmt(floor.elevation)} m).",
            ))
            floor.elevation = round(elevation, 4)
        elevation += floor.height


def _fill_room_heights(spec: BuildingSpecification) -> None:
    # Defaulting, not correcting: an omitted height means "full clear height of the floor".
    heights = {f.level: f.height - spec.building.slab_thickness for f in spec.floors}
    for room in spec.rooms:
        if room.height is None and room.floor in heights:
            room.height = round(heights[room.floor], 4)


def _snap_rooms_to_footprint(spec: BuildingSpecification, fixes: list[AppliedFix]) -> None:
    footprint = Rect(0, 0, spec.building.width, spec.building.depth)
    for room in spec.rooms:
        overhang = Rect(room.x, room.y, room.width, room.depth).overhang(footprint)
        if not overhang or max(overhang.values()) > SNAP_LIMIT:
            continue
        if room.x < 0:
            room.width += room.x
            room.x = 0.0
        if room.y < 0:
            room.depth += room.y
            room.y = 0.0
        room.width = min(room.width, footprint.width - room.x)
        room.depth = min(room.depth, footprint.depth - room.y)
        worst = max(overhang.values())
        fixes.append(AppliedFix(
            code="room_snapped_to_footprint",
            message=f"Trimmed {room.name} by {fmt(worst)} m so it fits inside the exterior walls.",
            element_ids=[room.id],
        ))


def _fix_stair_rise(spec: BuildingSpecification, fixes: list[AppliedFix]) -> None:
    floors = {f.level: f for f in spec.floors}
    for stair in spec.stairs:
        lower, upper = floors.get(stair.from_floor), floors.get(stair.to_floor)
        if lower is None or upper is None or upper.elevation <= lower.elevation:
            continue
        floor_to_floor = upper.elevation - lower.elevation
        if abs(stair.rise * stair.risers - floor_to_floor) <= ELEVATION_TOLERANCE:
            continue
        corrected = floor_to_floor / stair.risers
        if MIN_RISE <= corrected <= MAX_RISE:
            fixes.append(AppliedFix(
                code="stair_rise_corrected",
                message=f"Set stair {stair.id} rise to {corrected * 1000:.0f} mm so its {stair.risers} risers "
                        f"exactly match the {fmt(floor_to_floor)} m floor-to-floor height.",
                element_ids=[stair.id],
            ))
            stair.rise = round(corrected, 5)


def _default_ridge_direction(spec: BuildingSpecification, fixes: list[AppliedFix]) -> None:
    roof = spec.roof
    if roof.type is RoofType.FLAT or roof.ridge_direction is not None:
        return
    roof.ridge_direction = ridge_axis(roof, spec.building.width, spec.building.depth)
    fixes.append(AppliedFix(
        code="roof_ridge_defaulted",
        message=f"Ridge direction was not set; ran it along the longer side ({roof.ridge_direction.value} axis).",
    ))


def _floor_to_ceiling_sills(spec: BuildingSpecification, fixes: list[AppliedFix]) -> None:
    for window in spec.windows:
        if window.style is WindowStyle.FLOOR_TO_CEILING and window.sill_height > 0:
            fixes.append(AppliedFix(
                code="window_sill_corrected",
                message=f"Set the sill of floor-to-ceiling window {window.id} to 0 m (was {fmt(window.sill_height)} m).",
                element_ids=[window.id],
            ))
            window.sill_height = 0.0
