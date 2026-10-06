"""ChangeSet: what Claude returns for a modification request, and the typed operations it contains.

Structured outputs limit unions and optional fields, so Claude returns every operation in one
flat shape: an `op` name plus key/value parameters. Each operation is then parsed into its
own strictly typed model here, so a wrong or missing parameter is caught and sent back.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.models.common import ElementId
from app.models.materials import HexColour, MaterialId
from app.models.roof import RoofType
from app.models.room import RoomType

OpName = Literal[
    "set_room_area", "set_room_width", "add_room", "remove_room", "rename_room", "set_room_side", "set_room_glazing",
    "set_roof", "add_balcony", "remove_balcony",
    "set_exterior_material", "set_room_finish", "add_window", "remove_window",
]


class Param(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    value: Annotated[str, StringConstraints(max_length=200)]


class RawOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: OpName
    params: list[Param] = Field(max_length=12)


class ChangeSet(BaseModel):
    """Claude's reply. `understood` is false when the request is not a change to this design."""

    model_config = ConfigDict(extra="forbid")

    understood: bool
    summary: Annotated[str, StringConstraints(max_length=400)]
    operations: list[RawOperation] = Field(max_length=20)
    assumptions: list[Annotated[str, StringConstraints(max_length=240)]] = Field(max_length=8)


# ----------------------------------------------------------------------------- typed operations

class Op(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# Layout operations: they change the design intent and the building is re-planned.
class SetRoomArea(Op):
    room_id: ElementId
    target_area: Annotated[float, Field(ge=1, le=400)]


class SetRoomWidth(Op):
    """Width across the house (along the front). Rooms on the same side of the hall change with it."""

    room_id: ElementId
    width: Annotated[float, Field(ge=1.5, le=40)]


class AddRoom(Op):
    room_id: ElementId
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    type: RoomType
    floor: Annotated[int, Field(ge=0, le=9)]
    target_area: Annotated[float, Field(ge=1, le=400)]
    connect_to: ElementId


class RemoveRoom(Op):
    room_id: ElementId


class RenameRoom(Op):
    room_id: ElementId
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)]


class SetRoomSide(Op):
    room_id: ElementId
    side: Literal["front", "rear", "left", "right", "any"]


class SetRoomGlazing(Op):
    room_id: ElementId
    glazing: Literal["none", "standard", "large", "floor_to_ceiling"]


class SetRoof(Op):
    type: RoofType | None = None
    pitch: Annotated[float, Field(ge=0, le=70)] | None = None
    material: MaterialId | None = None


class AddBalcony(Op):
    room_id: ElementId


class RemoveBalcony(Op):
    room_id: ElementId


# Finishing operations: kept as overrides and re-applied after every re-plan.
class SetExteriorMaterial(Op):
    surface: Literal["wall", "accent", "trim", "window_frame", "door"]
    material: MaterialId
    colour: HexColour | None = None


class SetRoomFinish(Op):
    room_id: ElementId
    surface: Literal["floor", "wall", "ceiling"]
    material: MaterialId
    colour: HexColour | None = None


class AddWindow(Op):
    room_id: ElementId
    side: Literal["front", "rear", "left", "right", "any"] = "any"
    size: Literal["standard", "large", "floor_to_ceiling"] = "standard"


class RemoveWindow(Op):
    window_id: ElementId


LAYOUT_OPS: dict[str, type[Op]] = {
    "set_room_area": SetRoomArea, "set_room_width": SetRoomWidth, "add_room": AddRoom, "remove_room": RemoveRoom, "rename_room": RenameRoom,
    "set_room_side": SetRoomSide, "set_room_glazing": SetRoomGlazing, "set_roof": SetRoof,
    "add_balcony": AddBalcony, "remove_balcony": RemoveBalcony,
}
FINISH_OPS: dict[str, type[Op]] = {
    "set_exterior_material": SetExteriorMaterial, "set_room_finish": SetRoomFinish,
    "add_window": AddWindow, "remove_window": RemoveWindow,
}
ALL_OPS = {**LAYOUT_OPS, **FINISH_OPS}


class Override(BaseModel):
    """A finishing operation stored with the design, in order, and re-applied after every re-plan."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_exterior_material", "set_room_finish", "add_window", "remove_window"]
    params: dict[str, str]

    def typed(self) -> Op:
        return FINISH_OPS[self.op].model_validate(self.params)


def parse_operation(raw: RawOperation) -> Op:
    """Typed operation, or ValueError with a message Claude can act on."""
    params: dict[str, str] = {}
    for p in raw.params:
        if p.key in params:
            raise ValueError(f"{raw.op}: parameter '{p.key}' is given twice.")
        params[p.key] = p.value
    model = ALL_OPS[raw.op]
    try:
        return model.model_validate({k: (None if v == "" else v) for k, v in params.items()})
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'params'}: {e['msg']}" for e in exc.errors(include_url=False))
        expected = ", ".join(model.model_fields)
        raise ValueError(f"{raw.op}: {problems} (expected parameters: {expected}).") from exc


