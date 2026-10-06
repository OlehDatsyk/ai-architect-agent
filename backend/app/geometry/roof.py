"""Roof calculations from the building footprint.

Rise is measured from wall-plate level and excludes the overhang.
"""

import math

from app.models.common import Axis
from app.models.roof import Roof, RoofType


def ridge_axis(roof: Roof, width: float, depth: float) -> Axis:
    """The ridge (or shed high edge) axis; defaults to the longer side."""
    if roof.ridge_direction is not None:
        return roof.ridge_direction
    return Axis.X if width >= depth else Axis.Y


def roof_span(roof: Roof, width: float, depth: float) -> float:
    """Horizontal distance the roof slopes across (perpendicular to the ridge)."""
    return depth if ridge_axis(roof, width, depth) is Axis.X else width


def roof_rise(roof: Roof, width: float, depth: float) -> float:
    if roof.type is RoofType.FLAT:
        return 0.0
    slope = math.tan(math.radians(roof.pitch))
    span = roof_span(roof, width, depth)
    if roof.type is RoofType.SHED:
        return span * slope
    return span / 2 * slope


def hip_ridge_length(roof: Roof, width: float, depth: float) -> float:
    """Ridge length of a hip roof. Negative means the ridge runs along the shorter side,
    which cannot be built with equal pitches on all four faces."""
    along = width if ridge_axis(roof, width, depth) is Axis.X else depth
    return along - roof_span(roof, width, depth)
