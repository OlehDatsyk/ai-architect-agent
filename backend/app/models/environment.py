"""Site around the building: ground, hard landscaping, planting, sky and sun."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from app.models.common import Coordinate, ElementId, Metres, SpecModel
from app.models.materials import MaterialId, MaterialRef


class SiteArea(SpecModel):
    """A rectangular area at ground level, positioned in building coordinates.
    Areas in front of the building have negative y."""

    id: ElementId
    x: Coordinate
    y: Coordinate
    width: Metres
    depth: Metres
    material: MaterialRef


class VegetationKind(StrEnum):
    TREE = "tree"
    SHRUB = "shrub"
    HEDGE = "hedge"


class Vegetation(SpecModel):
    id: ElementId
    kind: VegetationKind
    x: Coordinate
    y: Coordinate
    size: Annotated[float, Field(gt=0, le=30)] = Field(description="Approximate height in metres.")


class Sun(SpecModel):
    azimuth_deg: Annotated[float, Field(ge=0, lt=360)] = 135
    elevation_deg: Annotated[float, Field(ge=0, le=90)] = 40


class Environment(SpecModel):
    ground_material: MaterialRef = Field(default_factory=lambda: MaterialRef(id=MaterialId.GRASS))
    driveway: SiteArea | None = None
    patio: SiteArea | None = None
    paths: list[SiteArea] = Field(default_factory=list, max_length=20)
    vegetation: list[Vegetation] = Field(default_factory=list, max_length=100)
    sky: Literal["clear", "overcast", "sunset"] = "clear"
    sun: Sun = Field(default_factory=Sun)
