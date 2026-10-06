"""Each test breaks a valid example in one specific way and checks the right rule fires."""

import pytest

from app.models import BuildingSpecification
from app.validation import Severity, ValidationStatus, validate_specification
from tests.helpers import codes, example, find, messages, report_for


def test_valid_example_passes() -> None:
    report = report_for(example())
    assert report.status is ValidationStatus.PASS
    assert report.issues == [] and report.fixes == []


# --- Schema -----------------------------------------------------------------------------

def test_negative_dimension_is_a_schema_error_with_location() -> None:
    data = example()
    data["rooms"][0]["width"] = -3
    result_report = report_for(data)
    assert result_report.status is ValidationStatus.ERROR
    issue = result_report.issues[0]
    assert issue.code == "schema_invalid" and issue.location == "rooms[0].width"


def test_missing_dimension_is_reported() -> None:
    data = example()
    del data["building"]["width"]
    assert any(i.location == "building.width" for i in report_for(data).issues)


# --- Structure ----------------------------------------------------------------------------

def test_duplicate_ids() -> None:
    data = example()
    find(data["rooms"], "bedroom_3")["id"] = "bedroom_2"
    assert "duplicate_id" in codes(report_for(data))


def test_floor_count_mismatch() -> None:
    data = example()
    data["building"]["floors"] = 3
    assert "floor_count_mismatch" in codes(report_for(data))


def test_floor_levels_with_gap() -> None:
    data = example()
    data["floors"][1]["level"] = 2
    assert "floor_levels_invalid" in codes(report_for(data))


def test_room_on_missing_floor() -> None:
    data = example()
    find(data["rooms"], "bedroom_3")["floor"] = 5
    assert "room_floor_missing" in codes(report_for(data))


# --- Rooms --------------------------------------------------------------------------------

def test_overlapping_rooms_reports_area() -> None:
    data = example()
    find(data["rooms"], "wc")["width"] = 2.2  # pushes the WC 1.0 m into the kitchen over 1.4 m
    report = report_for(data)
    assert "WC overlaps Kitchen / Dining by 1.40 m²." in messages(report)


def test_room_outside_footprint() -> None:
    data = example()
    find(data["rooms"], "living_room")["width"] += 1.0
    report = report_for(data)
    assert "room_outside_footprint" in codes(report)
    assert any("1.00 m beyond the right wall" in m for m in messages(report))


def test_tiny_overshoot_is_snapped_and_reported_as_fix() -> None:
    data = example()
    find(data["rooms"], "living_room")["width"] += 0.03
    result = validate_data_result(data)
    assert result.report.status is ValidationStatus.PASS
    assert [f.code for f in result.report.fixes] == ["room_snapped_to_footprint"]
    living = next(r for r in result.specification.rooms if r.id == "living_room")
    assert living.x + living.width == pytest.approx(9.6)


def test_room_too_narrow_is_error_and_small_room_is_warning() -> None:
    data = example()
    find(data["rooms"], "wardrobe")["depth"] = 0.5
    find(data["rooms"], "bedroom_2")["depth"] = 2.8  # 2.2 x 2.8 = 6.16 m², below 6.5
    report = report_for(data)
    assert "room_too_narrow" in codes(report)
    small = next(i for i in report.issues if i.code == "room_small")
    assert small.severity is Severity.WARNING


def test_room_taller_than_floor_allows() -> None:
    data = example()
    find(data["rooms"], "living_room")["height"] = 3.0
    assert "room_height_exceeds_floor" in codes(report_for(data))


def test_upper_room_over_empty_space_warns() -> None:
    data = example()
    data["rooms"] = [r for r in data["rooms"] if r["id"] != "utility"]
    data["doors"] = [d for d in data["doors"] if "utility" not in (d["connects_room_a"], d.get("connects_room_b"))]
    data["windows"] = [w for w in data["windows"] if w["room"] != "utility"]
    report = report_for(data)
    unsupported = [i for i in report.issues if i.code == "room_unsupported"]
    assert unsupported and unsupported[0].element_ids == ["bedroom_3"]


def test_unusual_material_warns() -> None:
    data = example()
    data["roof"]["material"] = "carpet"
    assert "material_unusual" in codes(report_for(data))


# --- Doors --------------------------------------------------------------------------------

def test_door_to_nonexistent_room() -> None:
    data = example()
    find(data["doors"], "door_hall_living")["connects_room_b"] = "ballroom"
    assert "door_room_missing" in codes(report_for(data))


def test_door_between_rooms_that_do_not_touch() -> None:
    data = example()
    find(data["doors"], "door_hall_wc")["connects_room_b"] = "utility"
    assert "door_rooms_not_adjacent" in codes(report_for(data))


def test_door_off_the_shared_wall() -> None:
    data = example()
    find(data["doors"], "door_hall_living")["position"]["y"] = 5.5
    assert "door_not_on_shared_wall" in codes(report_for(data))


def test_external_door_on_interior_wall() -> None:
    data = example()
    find(data["doors"], "door_front")["position"]["y"] = 2.0
    assert "door_not_on_exterior_wall" in codes(report_for(data))


def test_external_door_with_two_rooms() -> None:
    data = example()
    find(data["doors"], "door_front")["connects_room_b"] = "living_room"
    assert "door_connection_invalid" in codes(report_for(data))


def test_door_taller_than_room() -> None:
    data = example()
    find(data["doors"], "door_landing_master")["height"] = 2.6
    assert "door_too_tall" in codes(report_for(data))


def test_upper_floor_external_door_needs_balcony() -> None:
    data = example("luxury-house")
    data["balconies"] = []
    assert "door_opens_onto_drop" in codes(report_for(data))


def test_balcony_without_door_warns() -> None:
    data = example("luxury-house")
    data["doors"] = [d for d in data["doors"] if d["id"] != "door_balcony"]
    report = report_for(data)
    assert report.status is ValidationStatus.WARNING
    assert codes(report) == {"balcony_without_door"}


# --- Windows ------------------------------------------------------------------------------

def test_window_in_missing_room() -> None:
    data = example()
    find(data["windows"], "win_bedroom_2")["room"] = "attic"
    assert "window_room_missing" in codes(report_for(data))


def test_window_on_wall_the_room_does_not_touch() -> None:
    data = example()
    find(data["windows"], "win_landing_front")["wall"] = "right"
    assert "window_not_on_exterior_wall" in codes(report_for(data))


def test_window_running_past_room_wall() -> None:
    data = example()
    find(data["windows"], "win_master_front")["offset"] = 9.5
    assert "window_outside_room_wall" in codes(report_for(data))


def test_window_above_ceiling() -> None:
    data = example()
    window = find(data["windows"], "win_bedroom_2")
    window["sill_height"], window["height"] = 1.5, 1.5
    assert "window_too_tall" in codes(report_for(data))


def test_overlapping_windows() -> None:
    data = example()
    clone = dict(find(data["windows"], "win_master_front"), id="win_master_extra", offset=7.9)
    data["windows"].append(clone)
    assert "openings_overlap" in codes(report_for(data))


def test_bedroom_without_window_warns_with_readable_message() -> None:
    data = example()
    data["windows"] = [w for w in data["windows"] if w["room"] != "bedroom_2"]
    report = report_for(data)
    assert report.status is ValidationStatus.WARNING
    assert "Bedroom 2 has no exterior window." in messages(report)


def test_floor_to_ceiling_sill_is_fixed() -> None:
    data = example("modern-bungalow")
    find(data["windows"], "win_living_rear_1")["sill_height"] = 0.2
    report = report_for(data)
    assert report.status is ValidationStatus.PASS
    assert [f.code for f in report.fixes] == ["window_sill_corrected"]


# --- Circulation --------------------------------------------------------------------------

def test_missing_entrance_does_not_flood_with_inaccessible_rooms() -> None:
    data = example()
    data["doors"] = [d for d in data["doors"] if not d["is_external"] or d["type"] == "garage"]
    found = codes(report_for(data))
    assert "missing_entrance" in found
    assert "room_inaccessible" not in found


def test_room_with_no_door_is_inaccessible() -> None:
    data = example()
    data["doors"] = [d for d in data["doors"] if d["id"] != "door_hall_wc"]
    report = report_for(data)
    inaccessible = [i for i in report.issues if i.code == "room_inaccessible"]
    assert [i.element_ids for i in inaccessible] == [["wc"]]


def test_upper_floor_without_stairs() -> None:
    data = example()
    data["stairs"] = []
    found = codes(report_for(data))
    assert {"floors_not_connected", "room_inaccessible"} <= found


def test_stair_to_missing_floor() -> None:
    data = example()
    data["stairs"][0]["to_floor"] = 2
    assert "stair_floor_missing" in codes(report_for(data))


def test_stair_going_down_is_invalid() -> None:
    data = example()
    data["stairs"][0]["from_floor"], data["stairs"][0]["to_floor"] = 1, 0
    assert "stair_floors_invalid" in codes(report_for(data))


def test_stair_arriving_outside_any_room() -> None:
    data = example()
    stair = data["stairs"][0]
    stair["direction"], stair["y"] = "rear_to_front", 0.0
    assert "stair_arrival_not_in_room" in codes(report_for(data))


def test_stair_rising_into_bedroom_warns() -> None:
    data = example()
    data["stairs"][0]["x"] = 8.0  # moves the flight into the living room / master bedroom
    assert "stair_rises_into_room" in codes(report_for(data))


def test_small_stair_rise_mismatch_is_fixed() -> None:
    data = example()
    data["stairs"][0]["rise"] = 0.2  # 14 x 0.2 = 2.8, floors are 2.7 apart
    result = validate_data_result(data)
    assert result.report.status is ValidationStatus.PASS
    assert [f.code for f in result.report.fixes] == ["stair_rise_corrected"]
    assert result.specification.stairs[0].rise == pytest.approx(2.7 / 14, abs=1e-4)


def test_stair_with_impossible_riser_count_is_an_error() -> None:
    data = example()
    data["stairs"][0]["risers"], data["stairs"][0]["rise"] = 10, 0.25  # would need 270 mm risers
    assert "stair_height_mismatch" in codes(report_for(data))


def test_steep_stair_warns() -> None:
    data = example()
    data["stairs"][0]["run"] = 0.18
    found = codes(report_for(data))
    assert {"stair_short_tread", "stair_steep_pitch"} <= found


def test_kitchen_without_link_to_living_space_warns() -> None:
    data = example()
    find(data["rooms"], "kitchen_dining")["type"] = "kitchen"
    assert "kitchen_isolated" in codes(report_for(data))


# --- Floors and roof ----------------------------------------------------------------------

def test_wrong_floor_elevation_is_fixed() -> None:
    data = example()
    data["floors"][1]["elevation"] = 3.0
    result = validate_data_result(data)
    assert result.report.status is ValidationStatus.PASS
    assert [f.code for f in result.report.fixes] == ["floor_elevation_corrected"]
    assert result.specification.floors[1].elevation == pytest.approx(2.7)


def test_flat_roof_with_steep_pitch() -> None:
    data = example("modern-bungalow")
    data["roof"]["pitch"] = 20
    assert "roof_pitch_invalid" in codes(report_for(data))


def test_gable_roof_too_steep() -> None:
    data = example()
    data["roof"]["pitch"] = 75
    assert "roof_pitch_invalid" in codes(report_for(data))


def test_hip_ridge_along_short_side() -> None:
    data = example("luxury-house")
    data["roof"]["ridge_direction"] = "y"
    assert "roof_ridge_invalid" in codes(report_for(data))


def test_missing_ridge_direction_is_defaulted() -> None:
    data = example()
    data["roof"]["ridge_direction"] = None
    result = validate_data_result(data)
    assert result.report.status is ValidationStatus.PASS
    assert result.specification.roof.ridge_direction == "x"


def test_patio_inside_building_warns() -> None:
    data = example()
    data["environment"]["patio"]["y"] = 5.0
    assert "site_area_inside_building" in codes(report_for(data))


# --- Report behaviour ---------------------------------------------------------------------

def test_errors_are_listed_before_warnings() -> None:
    data = example()
    data["windows"] = [w for w in data["windows"] if w["room"] != "bedroom_2"]  # warning
    find(data["rooms"], "living_room")["width"] += 1.0                            # error
    report = report_for(data)
    assert report.status is ValidationStatus.ERROR
    assert report.issues[0].severity is Severity.ERROR
    assert report.error_count >= 1 and report.warning_count >= 1


def test_fixes_do_not_mutate_the_input_specification() -> None:
    data = example()
    data["floors"][1]["elevation"] = 3.0
    spec = BuildingSpecification.model_validate(data)
    validate_specification(spec)
    assert spec.floors[1].elevation == 3.0


def validate_data_result(data):
    from app.validation import validate_data
    return validate_data(data)
