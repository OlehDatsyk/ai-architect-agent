"""Typed architectural data model. See docs/building-specification.md."""

from app.models.building import (
    SCHEMA_VERSION,
    ArchitecturalStyle,
    BuildingInfo,
    BuildingSpecification,
    BuildingType,
    Exterior,
    Floor,
    ProjectInfo,
)
from app.models.common import Axis, Point2D, Side
from app.models.environment import Environment, SiteArea, Sun, Vegetation, VegetationKind
from app.models.materials import MaterialId, MaterialRef, MaterialUse
from app.models.opening import Balcony, Door, DoorType, Window, WindowStyle
from app.models.roof import Roof, RoofType
from app.models.room import Room, RoomType
from app.models.stairs import Stair, StairDirection

__all__ = [
    "SCHEMA_VERSION", "ArchitecturalStyle", "Axis", "Balcony", "BuildingInfo", "BuildingSpecification",
    "BuildingType", "Door", "DoorType", "Environment", "Exterior", "Floor", "MaterialId", "MaterialRef",
    "MaterialUse", "Point2D", "ProjectInfo", "Roof", "RoofType", "Room", "RoomType", "Side", "SiteArea",
    "Stair", "StairDirection", "Sun", "Vegetation", "VegetationKind", "Window", "WindowStyle",
]
