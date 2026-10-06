"""Roof definition. Geometry is calculated from the footprint (see app.geometry.roof)."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from app.models.common import Axis, SpecModel
from app.models.materials import MaterialRef


class RoofType(StrEnum):
    FLAT = "flat"
    GABLE = "gable"
    HIP = "hip"
    SHED = "shed"


class Roof(SpecModel):
    """Pitch is in degrees. For gable and hip roofs `ridge_direction` is the axis the ridge
    runs along; for shed roofs it is the axis of the high edge. Flat roofs ignore it."""

    type: RoofType
    pitch: Annotated[float, Field(ge=0, le=80)]
    overhang: Annotated[float, Field(ge=0, le=3)] = 0.3
    material: MaterialRef
    ridge_direction: Axis | None = None
