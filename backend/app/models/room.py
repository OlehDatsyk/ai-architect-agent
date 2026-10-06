"""Rooms: axis-aligned rectangles on a floor."""

from enum import StrEnum

from pydantic import computed_field, model_validator

from app.models.common import Coordinate, ElementId, FloorLevel, Metres, Name, SpecModel
from app.models.materials import MaterialId, MaterialRef


class RoomType(StrEnum):
    ENTRANCE = "entrance"
    HALLWAY = "hallway"
    LANDING = "landing"
    LIVING_ROOM = "living_room"
    KITCHEN = "kitchen"
    DINING_ROOM = "dining_room"
    KITCHEN_DINING = "kitchen_dining"
    OPEN_PLAN_LIVING = "open_plan_living"  # kitchen, dining and living in one space
    BEDROOM = "bedroom"
    BATHROOM = "bathroom"
    ENSUITE = "ensuite"
    WC = "wc"
    OFFICE = "office"
    UTILITY = "utility"
    GARAGE = "garage"
    STORAGE = "storage"
    RECEPTION = "reception"
    WORKSPACE = "workspace"
    MEETING_ROOM = "meeting_room"


CIRCULATION_ROOMS = frozenset({RoomType.ENTRANCE, RoomType.HALLWAY, RoomType.LANDING, RoomType.RECEPTION})

# Rooms people spend time in, which are expected to have at least one window.
HABITABLE_ROOMS = frozenset({
    RoomType.LIVING_ROOM, RoomType.KITCHEN, RoomType.DINING_ROOM, RoomType.KITCHEN_DINING,
    RoomType.OPEN_PLAN_LIVING, RoomType.BEDROOM, RoomType.OFFICE, RoomType.WORKSPACE,
    RoomType.MEETING_ROOM, RoomType.RECEPTION,
})

KITCHEN_CONNECTED_ROOMS = frozenset({
    RoomType.DINING_ROOM, RoomType.LIVING_ROOM, RoomType.KITCHEN_DINING, RoomType.OPEN_PLAN_LIVING,
})

WET_ROOMS = frozenset({RoomType.BATHROOM, RoomType.ENSUITE, RoomType.WC, RoomType.UTILITY})

# (wall, floor, ceiling) used when a room does not specify its own finishes.
_DEFAULT_FINISHES: dict[RoomType, tuple[MaterialId, MaterialId, MaterialId]] = {
    RoomType.GARAGE: (MaterialId.PAINTED_PLASTER, MaterialId.CONCRETE, MaterialId.PAINTED_PLASTER),
    RoomType.BEDROOM: (MaterialId.PAINTED_PLASTER, MaterialId.CARPET, MaterialId.PAINTED_PLASTER),
    RoomType.LANDING: (MaterialId.PAINTED_PLASTER, MaterialId.CARPET, MaterialId.PAINTED_PLASTER),
    RoomType.MEETING_ROOM: (MaterialId.PAINTED_PLASTER, MaterialId.CARPET, MaterialId.PAINTED_PLASTER),
    RoomType.WORKSPACE: (MaterialId.PAINTED_PLASTER, MaterialId.CARPET, MaterialId.PAINTED_PLASTER),
    **dict.fromkeys(WET_ROOMS, (MaterialId.TILE, MaterialId.TILE, MaterialId.PAINTED_PLASTER)),
    RoomType.KITCHEN: (MaterialId.PAINTED_PLASTER, MaterialId.TILE, MaterialId.PAINTED_PLASTER),
}
_FALLBACK_FINISHES = (MaterialId.PAINTED_PLASTER, MaterialId.WOOD_FLOORING, MaterialId.PAINTED_PLASTER)


class Room(SpecModel):
    """(x, y) is the room's front-left corner; width runs along X and depth along Y."""

    DERIVED_FIELDS = frozenset({"area"})

    id: ElementId
    name: Name
    type: RoomType
    floor: FloorLevel
    x: Coordinate
    y: Coordinate
    width: Metres
    depth: Metres
    # Clear floor-to-ceiling height. Omitted means: floor height minus slab thickness.
    height: Metres | None = None
    wall_material: MaterialRef | None = None
    floor_material: MaterialRef | None = None
    ceiling_material: MaterialRef | None = None

    @model_validator(mode="after")
    def _default_finishes(self) -> "Room":
        wall, floor, ceiling = _DEFAULT_FINISHES.get(self.type, _FALLBACK_FINISHES)
        self.wall_material = self.wall_material or MaterialRef(id=wall)
        self.floor_material = self.floor_material or MaterialRef(id=floor)
        self.ceiling_material = self.ceiling_material or MaterialRef(id=ceiling)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def area(self) -> float:
        return round(self.width * self.depth, 3)
