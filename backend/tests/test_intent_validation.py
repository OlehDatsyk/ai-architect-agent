from app.models.intent import DesignConstraints, DesignIntent
from app.validation import ValidationStatus
from app.validation.intent import apply_constraints, garage_size, validate_intent
from tests.intent_fixtures import british_house_intent


def check(data: dict, **constraints):
    return validate_intent(DesignIntent.model_validate(data), DesignConstraints(**constraints))


def codes(report) -> set[str]:
    return {i.code for i in report.issues}


def test_fixture_is_valid() -> None:
    assert check(british_house_intent()).error_count == 0


def test_duplicate_room_ids() -> None:
    data = british_house_intent()
    data["rooms"][2]["id"] = "hall"
    assert "duplicate_id" in codes(check(data))


def test_room_on_floor_that_does_not_exist() -> None:
    data = british_house_intent()
    data["rooms"][-1]["floor"] = 2
    assert "room_floor_missing" in codes(check(data))


def test_garage_upstairs() -> None:
    data = british_house_intent()
    next(r for r in data["rooms"] if r["id"] == "garage")["floor"] = 1
    assert "garage_not_on_ground" in codes(check(data))


def test_floor_area_larger_than_footprint() -> None:
    data = british_house_intent()
    data["footprint_width"], data["footprint_depth"] = 6, 6
    report = check(data)
    assert "floor_area_exceeds_footprint" in codes(report)
    assert any("6 x 6 m footprint is only 36 m²" in i.message for i in report.issues)


def test_underfilled_floor_warns() -> None:
    data = british_house_intent()
    data["footprint_width"], data["footprint_depth"] = 12, 10
    report = check(data)
    assert report.status is ValidationStatus.WARNING and "floor_underfilled" in codes(report)


def test_entrance_must_be_on_ground_floor() -> None:
    data = british_house_intent()
    data["entrance_room"] = "landing"
    assert "entrance_missing" in codes(check(data))


def test_connection_across_floors() -> None:
    data = british_house_intent()
    data["connections"].append({"room_a": "hall", "room_b": "landing", "kind": "door"})
    assert "connection_invalid" in codes(check(data))


def test_connection_to_unknown_room() -> None:
    data = british_house_intent()
    data["connections"].append({"room_a": "hall", "room_b": "cellar", "kind": "door"})
    assert "connection_room_missing" in codes(check(data))


def test_missing_stairs_and_unreachable_upper_floor() -> None:
    data = british_house_intent()
    data["stairs"] = []
    found = codes(check(data))
    assert {"floors_not_connected", "room_inaccessible"} <= found


def test_stair_rooms_on_wrong_floors() -> None:
    data = british_house_intent()
    data["stairs"][0]["arrival_room"] = "living_room"
    assert "stair_room_invalid" in codes(check(data))


def test_stair_starting_in_living_room_warns() -> None:
    data = british_house_intent()
    data["stairs"][0]["start_room"] = "living_room"
    report = check(data)
    assert "stair_in_room" in codes(report) and report.error_count == 0


def test_kitchen_must_reach_living_space() -> None:
    data = british_house_intent()
    next(r for r in data["rooms"] if r["id"] == "kitchen_dining")["type"] = "kitchen"
    assert "kitchen_isolated" in codes(check(data))


def test_balcony_on_ground_floor_room() -> None:
    data = british_house_intent()
    data["site"]["balcony_rooms"] = ["living_room"]
    assert "balcony_invalid" in codes(check(data))


def test_flat_roof_pitch() -> None:
    data = british_house_intent()
    data["roof"] = {"type": "flat", "pitch": 20, "material": "flat_roofing"}
    assert "roof_pitch_invalid" in codes(check(data))


def test_constraint_counts() -> None:
    report = check(british_house_intent(), bedrooms=4, bathrooms=2, floors=2, garage="double")
    messages = [i.message for i in report.issues if i.code == "constraint_not_met"]
    assert messages == [
        "The user requires bedrooms = 4, but the design has 3.",
        "The user requires garage = double, but the design has single.",
    ]


def test_height_constraint() -> None:
    assert "constraint_not_met" in codes(check(british_house_intent(), height=4))


def test_garage_size_from_area() -> None:
    intent = DesignIntent.model_validate(british_house_intent())
    assert garage_size(intent) == "single"


def test_apply_constraints_does_not_mutate_input() -> None:
    intent = DesignIntent.model_validate(british_house_intent())
    updated, notes = apply_constraints(intent, DesignConstraints(width=11, roof="hip"))
    assert intent.footprint_width == 9.6 and updated.footprint_width == 11
    assert updated.roof.type == "hip" and len(notes) == 2


def test_unchanged_constraints_produce_no_notes() -> None:
    intent = DesignIntent.model_validate(british_house_intent())
    _, notes = apply_constraints(intent, DesignConstraints(style="contemporary", roof="gable"))
    assert notes == []
