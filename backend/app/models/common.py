"""Shared building blocks for the BuildingSpecification models.

Coordinate system (metres throughout):
    X = building width, left to right as seen from the front
    Y = building depth, front (y = 0) to rear (y = building.depth)
    Z = up; z = 0 is ground-floor finished floor level
    Origin = front-left corner of the building footprint.
"""

from enum import StrEnum
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ElementId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=80)]
Metres = Annotated[float, Field(gt=0, le=200)]
NonNegativeMetres = Annotated[float, Field(ge=0, le=200)]
Coordinate = Annotated[float, Field(ge=-500, le=500)]
FloorLevel = Annotated[int, Field(ge=0, le=9)]


class Side(StrEnum):
    """An exterior wall of the rectangular footprint."""

    FRONT = "front"  # y = 0
    REAR = "rear"    # y = depth
    LEFT = "left"    # x = 0
    RIGHT = "right"  # x = width


class Axis(StrEnum):
    X = "x"
    Y = "y"


class SpecModel(BaseModel):
    """Base for every specification model.

    Unknown keys are rejected so typos in AI or user input fail loudly. Keys listed in
    DERIVED_FIELDS are output-only (computed fields) and are dropped on input, which lets
    a dumped specification be loaded again without contradicting itself.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    DERIVED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _drop_derived_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and cls.DERIVED_FIELDS:
            return {k: v for k, v in data.items() if k not in cls.DERIVED_FIELDS}
        return data


class Point2D(SpecModel):
    x: Coordinate
    y: Coordinate
