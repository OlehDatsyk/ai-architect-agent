import math

import pytest
from pydantic import ValidationError

from app.models import BuildingSpecification, MaterialId, MaterialRef, Room, RoomType
from tests.helpers import example, find


def test_example_parses_into_typed_models() -> None:
    spec = BuildingSpecification.model_validate(example())
    assert spec.schema_version == "1.0"
    assert spec.project.units == "metres"
    assert len(spec.rooms_on_floor(0)) == 6
    assert spec.floor(1) is not None and spec.floor(1).name == "First floor"


def test_dump_includes_derived_fields() -> None:
    spec = BuildingSpecification.model_validate(example())
    dumped = spec.model_dump(mode="json")
    living = find(dumped["rooms"], "living_room")
    assert living["area"] == pytest.approx(4.4 * 4.6)
    # 2.7 + 2.6 walls plus a 35° gable over 8.5 m depth.
    assert dumped["total_height"] == pytest.approx(5.3 + 4.25 * math.tan(math.radians(35)), abs=0.001)


def test_json_round_trip_is_stable() -> None:
    spec = BuildingSpecification.model_validate(example())
    again = BuildingSpecification.model_validate_json(spec.model_dump_json())
    assert again == spec


def test_derived_fields_in_input_are_ignored_not_trusted() -> None:
    data = example()
    find(data["rooms"], "living_room")["area"] = 999
    data["total_height"] = 999
    spec = BuildingSpecification.model_validate(data)
    assert next(r for r in spec.rooms if r.id == "living_room").area == pytest.approx(20.24)
    assert spec.total_height < 20


def test_unknown_keys_are_rejected() -> None:
    data = example()
    data["rooms"][0]["widht"] = 3
    with pytest.raises(ValidationError, match="widht"):
        BuildingSpecification.model_validate(data)


@pytest.mark.parametrize("bad_id", ["Bedroom", "1room", "room-1", "room 1", ""])
def test_element_ids_must_be_snake_case(bad_id: str) -> None:
    data = example()
    data["rooms"][0]["id"] = bad_id
    with pytest.raises(ValidationError):
        BuildingSpecification.model_validate(data)


def test_material_shorthand_and_colour() -> None:
    assert MaterialRef.model_validate("brick") == MaterialRef(id=MaterialId.BRICK)
    assert MaterialRef.model_validate({"id": "brick", "colour": "#7a3b2e"}).colour == "#7a3b2e"
    with pytest.raises(ValidationError):
        MaterialRef.model_validate({"id": "brick", "colour": "red"})
    with pytest.raises(ValidationError):
        MaterialRef.model_validate("marble")


def test_room_finishes_default_by_type() -> None:
    bedroom = Room(id="b", name="Bed", type=RoomType.BEDROOM, floor=1, x=0, y=0, width=3, depth=3)
    bathroom = Room(id="w", name="Bath", type=RoomType.BATHROOM, floor=1, x=0, y=0, width=2, depth=2)
    assert bedroom.floor_material and bedroom.floor_material.id is MaterialId.CARPET
    assert bathroom.wall_material and bathroom.wall_material.id is MaterialId.TILE


def test_explicit_finish_is_kept() -> None:
    room = Room(id="b", name="Bed", type=RoomType.BEDROOM, floor=0, x=0, y=0, width=3, depth=3, floor_material="wood_flooring")
    assert room.floor_material and room.floor_material.id is MaterialId.WOOD_FLOORING


def test_json_schema_is_generated() -> None:
    schema = BuildingSpecification.model_json_schema()
    assert "rooms" in schema["properties"]
    assert "Room" in schema["$defs"]
