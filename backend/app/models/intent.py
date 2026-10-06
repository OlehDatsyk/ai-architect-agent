"""Design intent: what Claude understood from a brief, before any coordinates exist.

Claude fills DesignIntent through structured outputs. It describes WHAT is needed (rooms,
sizes, connections, stairs, roof, materials); the deterministic planner (Phase 4) decides
WHERE things go. Every field is required and nullable fields are kept to a minimum, because
structured-output schemas are limited to 24 optional and 16 union-typed parameters.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.building import ArchitecturalStyle, BuildingType
from app.models.common import ElementId, Name
from app.models.materials import MaterialId
from app.models.roof import RoofType
from app.models.room import RoomType

Glazing = Literal["none", "standard", "large", "floor_to_ceiling"]
PreferredSide = Literal["front", "rear", "left", "right", "any"]
GarageSize = Literal["none", "single", "double"]


class IntentModel(BaseModel):
    """Strict base that also lower-cases enum strings: structured outputs do not guarantee
    the capitalisation of enum values, and every enum here is lower-case."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _normalise_enum_case(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        enum_fields = {name for name, f in cls.model_fields.items() if _is_enum_like(f.annotation)}
        return {k: v.lower() if k in enum_fields and isinstance(v, str) else v for k, v in data.items()}


def _is_enum_like(annotation: Any) -> bool:
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return True
    return getattr(annotation, "__origin__", None) is Literal


class IntentRoom(IntentModel):
    id: ElementId = Field(description="Unique snake_case ID, e.g. bedroom_2.")
    name: Name = Field(description="Display name, e.g. 'Bedroom 2'.")
    type: RoomType
    floor: Annotated[int, Field(ge=0, le=9)] = Field(description="0 = ground floor.")
    target_area: Annotated[float, Field(ge=1, le=400)] = Field(description="Target floor area in square metres.")
    glazing: Glazing = Field(description="How much window the room should have.")
    preferred_side: PreferredSide = Field(description="Exterior wall the room should face, if it matters.")


class IntentConnection(IntentModel):
    room_a: ElementId
    room_b: ElementId
    kind: Literal["door", "open"] = Field(description="'open' for open-plan spaces with no door between them.")


class IntentStair(IntentModel):
    from_floor: Annotated[int, Field(ge=0, le=9)]
    to_floor: Annotated[int, Field(ge=0, le=9)]
    start_room: ElementId = Field(description="Room on from_floor where the stair starts (usually a hall).")
    arrival_room: ElementId = Field(description="Room on to_floor where the stair arrives (usually a landing).")


class IntentRoof(IntentModel):
    type: RoofType
    pitch: Annotated[float, Field(ge=0, le=70)] = Field(description="Degrees. Flat roofs use 1-3.")
    material: MaterialId


class IntentExterior(IntentModel):
    wall_material: MaterialId
    accent_material: MaterialId | None = Field(description="Secondary facade material, or null.")
    window_frame_material: MaterialId


class IntentSite(IntentModel):
    driveway: bool
    patio: bool
    balcony_rooms: list[ElementId] = Field(description="IDs of upper-floor rooms that get a balcony.")


class DesignIntent(IntentModel):
    understood: bool = Field(description="False if the brief is not a request to design a building.")
    project_name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    summary: Annotated[str, StringConstraints(max_length=600)] = Field(description="One or two sentences describing the design.")
    building_type: BuildingType
    style: ArchitecturalStyle
    floors: Annotated[int, Field(ge=1, le=10)]
    floor_height: Annotated[float, Field(ge=2.3, le=5.0)] = Field(description="Floor-to-floor height in metres.")
    footprint_width: Annotated[float, Field(ge=4, le=80)] = Field(description="Metres along the front (street) side.")
    footprint_depth: Annotated[float, Field(ge=4, le=80)] = Field(description="Metres from front to rear.")
    entrance_room: ElementId = Field(description="Ground-floor room the front door opens into.")
    rooms: list[IntentRoom] = Field(min_length=1, max_length=60)
    connections: list[IntentConnection] = Field(max_length=150)
    stairs: list[IntentStair] = Field(max_length=10)
    roof: IntentRoof
    exterior: IntentExterior
    site: IntentSite
    assumptions: list[Annotated[str, StringConstraints(max_length=240)]] = Field(
        max_length=12, description="Decisions made where the brief was silent, in plain English."
    )

    def rooms_on_floor(self, level: int) -> list[IntentRoom]:
        return [r for r in self.rooms if r.floor == level]


# ---------------------------------------------------------------------------- API request

RoofChoice = Literal["automatic", "flat", "gable", "hip", "shed"]
DetailLevel = Literal["concept", "standard", "detailed"]


class DesignConstraints(BaseModel):
    """Optional advanced controls. When set they override whatever the brief implies."""

    model_config = ConfigDict(extra="forbid")

    building_type: BuildingType | None = None
    style: ArchitecturalStyle | None = None
    floors: Annotated[int, Field(ge=1, le=10)] | None = None
    width: Annotated[float, Field(ge=4, le=80)] | None = None
    depth: Annotated[float, Field(ge=4, le=80)] | None = None
    height: Annotated[float, Field(ge=3, le=40)] | None = None
    bedrooms: Annotated[int, Field(ge=0, le=12)] | None = None
    bathrooms: Annotated[int, Field(ge=0, le=10)] | None = None
    garage: GarageSize | None = None
    roof: RoofChoice = "automatic"
    detail_level: DetailLevel = "standard"


class DesignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prompt: Annotated[str, StringConstraints(min_length=10, max_length=4000)]
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)
