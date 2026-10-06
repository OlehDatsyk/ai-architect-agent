"""Straight-flight stairs."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from app.models.common import Coordinate, ElementId, FloorLevel, SpecModel


class StairDirection(StrEnum):
    """Direction of travel going up."""

    FRONT_TO_REAR = "front_to_rear"  # +Y
    REAR_TO_FRONT = "rear_to_front"  # -Y
    LEFT_TO_RIGHT = "left_to_right"  # +X
    RIGHT_TO_LEFT = "right_to_left"  # -X


class Stair(SpecModel):
    """(x, y) is the front-left corner of the stair footprint.

    `risers` is the number of rises between floors; the flight has risers - 1 treads,
    so its plan length is run * (risers - 1).
    """

    id: ElementId
    from_floor: FloorLevel
    to_floor: FloorLevel
    x: Coordinate
    y: Coordinate
    width: Annotated[float, Field(ge=0.5, le=4)]
    direction: StairDirection
    risers: Annotated[int, Field(ge=2, le=40)]
    rise: Annotated[float, Field(gt=0, le=0.4)]
    run: Annotated[float, Field(gt=0, le=0.6)]
