"""Roof parameters that cannot be built, or are unusual."""

from collections.abc import Iterator

from app.geometry.roof import hip_ridge_length
from app.models.roof import RoofType
from app.validation.context import ValidationContext, fmt
from app.validation.report import ValidationIssue, error, warning

MAX_FLAT_PITCH = 5.0
MIN_PITCHED = 5.0
MAX_PITCHED = 70.0
TYPICAL_PITCH = {RoofType.GABLE: (15.0, 55.0), RoofType.HIP: (15.0, 55.0), RoofType.SHED: (3.0, 30.0)}


def check_roof(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    roof, b = ctx.spec.roof, ctx.spec.building
    if roof.type is RoofType.FLAT:
        if roof.pitch > MAX_FLAT_PITCH:
            yield error("roof_pitch_invalid", f"A flat roof cannot have a {roof.pitch:.0f}° pitch (maximum {MAX_FLAT_PITCH:.0f}°). Use a shed roof instead.")
    else:
        if roof.pitch < MIN_PITCHED or roof.pitch > MAX_PITCHED:
            yield error("roof_pitch_invalid", f"A {roof.type.value} roof needs a pitch between {MIN_PITCHED:.0f}° and {MAX_PITCHED:.0f}° (got {roof.pitch:.0f}°).")
        else:
            low, high = TYPICAL_PITCH[roof.type]
            if not low <= roof.pitch <= high:
                yield warning("roof_pitch_unusual", f"A {roof.pitch:.0f}° pitch is unusual for a {roof.type.value} roof (typically {low:.0f}-{high:.0f}°).")
    if roof.type is RoofType.HIP and hip_ridge_length(roof, b.width, b.depth) < 0:
        yield error("roof_ridge_invalid", "A hip roof's ridge must run along the longer side of the building.")
    if roof.overhang > 1.2:
        yield warning("roof_overhang_large", f"A {fmt(roof.overhang)} m roof overhang is unusually large.")
