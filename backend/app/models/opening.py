"""Doors, windows and balconies."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from app.models.common import Axis, Coordinate, ElementId, FloorLevel, Point2D, Side, SpecModel
from app.models.materials import MaterialId, MaterialRef

OpeningWidth = Annotated[float, Field(gt=0, le=6)]
OpeningHeight = Annotated[float, Field(gt=0, le=5)]


class DoorType(StrEnum):
    INTERNAL = "internal"
    FRONT = "front"
    REAR = "rear"
    PATIO_SLIDING = "patio_sliding"
    GARAGE = "garage"
    OPENING = "opening"  # a doorless opening, e.g. between open-plan spaces


EXTERNAL_DOOR_TYPES = frozenset({DoorType.FRONT, DoorType.REAR, DoorType.PATIO_SLIDING, DoorType.GARAGE})
PEDESTRIAN_ENTRANCE_TYPES = frozenset({DoorType.FRONT, DoorType.REAR, DoorType.PATIO_SLIDING})


class Door(SpecModel):
    """A door centred at `position` on a wall centreline.

    rotation 0 or 180: the door sits in a wall running along X (constant y).
    rotation 90 or 270: the door sits in a wall running along Y (constant x).
    External doors leave connects_room_b empty.
    """

    id: ElementId
    type: DoorType
    floor: FloorLevel
    position: Point2D
    rotation: Literal[0, 90, 180, 270]
    width: OpeningWidth
    height: OpeningHeight = 2.1
    connects_room_a: ElementId
    connects_room_b: ElementId | None = None
    is_external: bool
    material: MaterialRef = Field(default_factory=lambda: MaterialRef(id=MaterialId.WOOD))

    @property
    def wall_axis(self) -> Axis:
        return Axis.X if self.rotation in (0, 180) else Axis.Y


class WindowStyle(StrEnum):
    FIXED = "fixed"
    CASEMENT = "casement"
    SLIDING = "sliding"
    FLOOR_TO_CEILING = "floor_to_ceiling"


class Window(SpecModel):
    """A window in an exterior wall. `offset` is the window centre measured along that wall
    in building coordinates: x for front/rear walls, y for left/right walls."""

    id: ElementId
    style: WindowStyle
    room: ElementId
    wall: Side
    offset: Coordinate
    width: OpeningWidth
    height: OpeningHeight
    sill_height: Annotated[float, Field(ge=0, le=5)] = 0.9


class Balcony(SpecModel):
    """A balcony projecting `depth` metres outward from an exterior wall of `room`."""

    id: ElementId
    room: ElementId
    wall: Side
    offset: Coordinate
    width: Annotated[float, Field(gt=0, le=20)]
    depth: Annotated[float, Field(gt=0, le=4)]
    railing_height: Annotated[float, Field(ge=0.8, le=1.5)] = 1.1
    floor_material: MaterialRef = Field(default_factory=lambda: MaterialRef(id=MaterialId.CONCRETE))
    railing_material: MaterialRef = Field(default_factory=lambda: MaterialRef(id=MaterialId.GLASS))
