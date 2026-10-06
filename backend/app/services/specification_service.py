"""Human-readable summary of a specification, used by the review screen (Phase 3+)."""

from typing import Literal

from pydantic import BaseModel

from app.models.building import BuildingSpecification
from app.models.room import RoomType

DOUBLE_GARAGE_MIN_WIDTH = 5.0


class FloorSummary(BaseModel):
    level: int
    name: str
    rooms: list[str]
    floor_area: float


class SpecificationSummary(BaseModel):
    project_name: str
    building_type: str
    style: str
    floors: int
    width: float
    depth: float
    total_height: float
    gross_floor_area: float
    bedrooms: int
    bathrooms: int
    wcs: int
    garage: Literal["none", "single", "double"]
    roof_type: str
    floor_details: list[FloorSummary]


def summarise(spec: BuildingSpecification) -> SpecificationSummary:
    rooms = spec.rooms
    garages = [r for r in rooms if r.type is RoomType.GARAGE]
    garage: Literal["none", "single", "double"] = "none"
    if garages:
        garage = "double" if max(min(g.width, g.depth) for g in garages) >= DOUBLE_GARAGE_MIN_WIDTH else "single"
    floor_details = [
        FloorSummary(
            level=f.level, name=f.name,
            rooms=[r.name for r in spec.rooms_on_floor(f.level)],
            floor_area=round(sum(r.area for r in spec.rooms_on_floor(f.level)), 2),
        )
        for f in sorted(spec.floors, key=lambda f: f.level)
    ]
    return SpecificationSummary(
        project_name=spec.project.name,
        building_type=spec.building.building_type.value,
        style=spec.project.style.value,
        floors=len(spec.floors),
        width=spec.building.width,
        depth=spec.building.depth,
        total_height=spec.total_height,
        gross_floor_area=round(sum(f.floor_area for f in floor_details), 2),
        bedrooms=sum(r.type is RoomType.BEDROOM for r in rooms),
        bathrooms=sum(r.type in (RoomType.BATHROOM, RoomType.ENSUITE) for r in rooms),
        wcs=sum(r.type is RoomType.WC for r in rooms),
        garage=garage,
        roof_type=spec.roof.type.value,
        floor_details=floor_details,
    )
