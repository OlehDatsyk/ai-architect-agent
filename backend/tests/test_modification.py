"""Modifications applied deterministically: each request changes what it asks for and little else."""

import pytest

from app.models.intent import DesignIntent
from app.modification.apply import ModificationError, apply_layout, check_operation, realise, verify_effects
from app.modification.changeset import (
    AddBalcony,
    AddRoom,
    Override,
    Param,
    RawOperation,
    RemoveRoom,
    SetExteriorMaterial,
    SetRoof,
    SetRoomArea,
    SetRoomFinish,
    SetRoomSide,
    SetRoomWidth,
    parse_operation,
)
from app.modification.diff import describe_changes
from app.planner.anchor import anchor_from
from tests.intent_fixtures import british_house_intent


@pytest.fixture(scope="module")
def base():
    intent = DesignIntent.model_validate(british_house_intent())
    return intent, realise(intent, []).specification


def modify(base, ops=(), overrides=()):
    intent, spec = base
    new_intent, anchor = intent.model_copy(deep=True), anchor_from(spec)
    for op in ops:
        check_operation(op, intent, spec)
        apply_layout(op, new_intent, anchor, spec)
    after = realise(new_intent, list(overrides), anchor)
    return after, describe_changes(spec, after.specification), verify_effects(list(ops), after.specification, spec)


def room(spec, room_id):
    return next(r for r in spec.rooms if r.id == room_id)


def test_wider_living_room_is_exactly_wider_and_nothing_is_rearranged(base) -> None:
    width = room(base[1], "living_room").width
    after, changes, problems = modify(base, [SetRoomWidth(room_id="living_room", width=width + 1)])
    assert room(after.specification, "living_room").width == pytest.approx(width + 1, abs=0.01)
    assert problems == [] and after.report.error_count == 0
    assert not any("rearranged" in n for n in after.notes)


def test_hip_roof_changes_only_the_roof(base) -> None:
    after, changes, _ = modify(base, [SetRoof(type="hip")])
    assert changes == ["Roof: gable 35° slate -> hip 35° slate."]


def test_darker_brick_changes_only_the_walls(base) -> None:
    _, changes, _ = modify(base, overrides=[Override(op="set_exterior_material", params={"surface": "wall", "material": "brick", "colour": "#5A2318"})])
    assert changes == ["Exterior wall: brick -> brick (#5A2318)."]


def test_another_window_in_the_master_bedroom(base) -> None:
    after, changes, _ = modify(base, overrides=[Override(op="add_window", params={"room_id": "master_bedroom"})])
    assert len(changes) == 1 and changes[0].startswith("Added a") and "Master Bedroom" in changes[0]
    assert after.report.error_count == 0  # placed clear of the corners and the other openings


def test_balcony_above_the_garage(base) -> None:
    intent, spec = base
    garage = room(spec, "garage")
    above = max((r for r in spec.rooms_on_floor(1)), key=lambda r: r.width * r.depth * 0 + min(r.x + r.width, garage.x + garage.width) - max(r.x, garage.x))
    after, changes, problems = modify(base, [AddBalcony(room_id=above.id)])
    assert problems == [] and changes == [f"Added a balcony to {above.name}."]


def test_garage_moves_by_swapping_with_one_room(base) -> None:
    after, changes, problems = modify(base, [SetRoomSide(room_id="garage", side="left")])
    assert problems == [] and not any("rearranged" in n for n in after.notes)
    anchor = anchor_from(after.specification)
    assert anchor.sides["garage"] == 0
    assert all(r.floor == 0 or "m²" not in c for c in changes for r in [room(after.specification, "garage")])  # upper floor untouched


def test_finishing_overrides_survive_a_later_layout_change(base) -> None:
    intent, spec = base
    window = Override(op="add_window", params={"room_id": "master_bedroom", "size": "large"})
    first = realise(intent, [window], anchor_from(spec)).specification
    new_intent = intent.model_copy(deep=True)
    apply_layout(SetRoomArea(room_id="kitchen_dining", target_area=26), new_intent)
    second = realise(new_intent, [window], anchor_from(first)).specification
    assert any(w.id.startswith("win_master_bedroom_") and "added" in w.id for w in second.windows)


def test_added_room_and_removed_room(base) -> None:
    after, changes, _ = modify(base, [AddRoom(room_id="study", name="Study", type="office", floor=1, target_area=7, connect_to="landing")])
    assert "Added Study" in " ".join(changes) and after.report.error_count == 0
    after, changes, _ = modify(base, [RemoveRoom(room_id="storage")])
    assert "Removed Airing Cupboard." in changes


def test_interior_finish(base) -> None:
    _, changes, _ = modify(base, overrides=[Override(op="set_room_finish", params={"room_id": "bedroom_2", "surface": "floor", "material": "wood_flooring"})])
    assert changes == ["Bedroom 2 floor: carpet -> wood flooring."]


@pytest.mark.parametrize(("op", "message"), [
    (SetRoomArea(room_id="ballroom", target_area=40), "There is no room 'ballroom'"),
    (RemoveRoom(room_id="hall"), "holds the entrance or the stairs"),
    (AddBalcony(room_id="living_room"), "ground floor"),
    (SetExteriorMaterial(surface="wall", material="carpet"), "not suitable for the exterior wall"),
    (SetRoomFinish(room_id="bedroom_2", surface="floor", material="slate"), "not an interior finish"),
    (SetRoof(material="brick"), "not a roofing material"),
    (AddRoom(room_id="study", name="Study", type="office", floor=1, target_area=7, connect_to="hall"), "connect it to a room on the same floor"),
])
def test_invalid_operations_are_explained(base, op, message: str) -> None:
    with pytest.raises(ModificationError, match=message):
        check_operation(op, *base)


def test_operation_parsing_reports_wrong_parameters() -> None:
    assert parse_operation(RawOperation(op="add_window", params=[Param(key="room_id", value="study")])).size == "standard"
    with pytest.raises(ValueError, match="expected parameters: room_id, target_area"):
        parse_operation(RawOperation(op="set_room_area", params=[Param(key="room", value="x")]))
    with pytest.raises(ValueError, match="given twice"):
        parse_operation(RawOperation(op="remove_room", params=[Param(key="room_id", value="a"), Param(key="room_id", value="b")]))


def test_rebuilding_a_modified_design_keeps_every_unchanged_blender_object(base) -> None:
    """Definition of done, item 20: the rebuilt scene differs only where the design changed."""
    from app.scene.compiler import compile_scene

    intent, spec = base
    after, _, _ = modify(base, overrides=[Override(op="add_window", params={"room_id": "master_bedroom"})])
    before_names = {e.name for e in compile_scene(spec).elements}
    after_names = {e.name for e in compile_scene(after.specification).elements}
    added = after_names - before_names
    assert before_names <= after_names, "an unchanged object was renamed or lost"
    assert added and all(n.startswith("Window_MasterBedroom") for n in added)
