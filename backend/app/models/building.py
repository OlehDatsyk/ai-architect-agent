"""The root BuildingSpecification: the contract between the AI, validator, planner and Blender."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, StringConstraints, computed_field

from app.geometry.roof import roof_rise
from app.models.common import FloorLevel, Name, SpecModel
from app.models.environment import Environment
from app.models.materials import MaterialId, MaterialRef
from app.models.opening import Balcony, Door, Window
from app.models.roof import Roof
from app.models.room import Room
from app.models.stairs import Stair

SCHEMA_VERSION = "1.0"


class BuildingType(StrEnum):
    DETACHED_HOUSE = "detached_house"
    SEMI_DETACHED_HOUSE = "semi_detached_house"
    BUNGALOW = "bungalow"
    APARTMENT_BUILDING = "apartment_building"
    OFFICE = "office"
    SHOP = "shop"
    CUSTOM = "custom"


class ArchitecturalStyle(StrEnum):
    MODERN = "modern"
    CONTEMPORARY = "contemporary"
    TRADITIONAL_BRITISH = "traditional_british"
    VICTORIAN_INSPIRED = "victorian_inspired"
    SCANDINAVIAN = "scandinavian"
    MEDITERRANEAN = "mediterranean"
    INDUSTRIAL = "industrial"
    MINIMALIST = "minimalist"
    CUSTOM = "custom"


class ProjectInfo(SpecModel):
    id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")] = Field(default_factory=lambda: uuid4().hex)
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    description: Annotated[str, StringConstraints(max_length=2000)] = ""
    units: Literal["metres"] = "metres"
    style: ArchitecturalStyle
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BuildingInfo(SpecModel):
    building_type: BuildingType
    width: Annotated[float, Field(gt=0, le=200)]
    depth: Annotated[float, Field(gt=0, le=200)]
    floors: Annotated[int, Field(ge=1, le=10)]
    floor_height: Annotated[float, Field(ge=2.0, le=8.0)] = Field(2.7, description="Default floor-to-floor height.")
    foundation_height: Annotated[float, Field(ge=0, le=2)] = 0.15
    wall_thickness: Annotated[float, Field(ge=0.05, le=1)] = 0.3
    interior_wall_thickness: Annotated[float, Field(ge=0.05, le=0.5)] = 0.1
    slab_thickness: Annotated[float, Field(ge=0.05, le=1)] = 0.25


class Floor(SpecModel):
    level: FloorLevel
    name: Name
    elevation: Annotated[float, Field(ge=0, le=100)] = Field(description="Finished floor level above ground floor.")
    height: Annotated[float, Field(ge=2.0, le=8.0)] = Field(description="Floor-to-floor height.")


class Exterior(SpecModel):
    wall_material: MaterialRef
    accent_material: MaterialRef | None = None
    trim_material: MaterialRef = Field(default_factory=lambda: MaterialRef(id=MaterialId.DARK_METAL))
    window_frame_material: MaterialRef = Field(default_factory=lambda: MaterialRef(id=MaterialId.ALUMINIUM))
    door_material: MaterialRef = Field(default_factory=lambda: MaterialRef(id=MaterialId.WOOD))


class BuildingSpecification(SpecModel):
    DERIVED_FIELDS = frozenset({"total_height"})

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project: ProjectInfo
    building: BuildingInfo
    floors: list[Floor] = Field(min_length=1, max_length=10)
    rooms: list[Room] = Field(min_length=1, max_length=200)
    doors: list[Door] = Field(default_factory=list, max_length=400)
    windows: list[Window] = Field(default_factory=list, max_length=400)
    stairs: list[Stair] = Field(default_factory=list, max_length=20)
    balconies: list[Balcony] = Field(default_factory=list, max_length=20)
    roof: Roof
    exterior: Exterior
    environment: Environment = Field(default_factory=Environment)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_height(self) -> float:
        """Ground floor level to the roof's highest point (wall plate plus roof rise)."""
        walls = max((f.elevation + f.height for f in self.floors), default=0.0)
        return round(walls + roof_rise(self.roof, self.building.width, self.building.depth), 3)

    def rooms_on_floor(self, level: int) -> list[Room]:
        return [room for room in self.rooms if room.floor == level]

    def floor(self, level: int) -> Floor | None:
        return next((f for f in self.floors if f.level == level), None)
