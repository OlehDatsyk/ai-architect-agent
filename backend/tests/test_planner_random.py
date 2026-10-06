"""Robustness: hundreds of generated intents must each either plan cleanly or fail clearly."""

import random

import pytest

from app.models.intent import DesignIntent
from app.planner import PlanningError, plan_building
from tests.test_planner import assert_sensible_route, front_door_reachability

ROOM_CHOICES = {
    0: [("living_room", 18, 30), ("kitchen", 9, 15), ("kitchen_dining", 18, 30), ("open_plan_living", 35, 60),
        ("dining_room", 9, 14), ("wc", 1.5, 3), ("utility", 4, 8), ("office", 7, 12), ("garage", 16, 34), ("storage", 2, 5)],
    1: [("bedroom", 8, 18), ("bathroom", 5, 9), ("ensuite", 3, 5), ("storage", 2, 5), ("office", 7, 11)],
}


def random_intent(rng: random.Random) -> dict:
    floors = rng.choice([1, 2, 2, 2, 3])
    width, depth = round(rng.uniform(8, 18), 1), round(rng.uniform(7.5, 12), 1)
    footprint = width * depth
    rooms, connections = [], []
    for level in range(floors):
        hall = "hall" if level == 0 else f"landing_{level}"
        rooms.append({"id": hall, "name": "Hall" if level == 0 else f"Landing {level}", "type": "entrance" if level == 0 else "landing",
                      "floor": level, "target_area": round(footprint * 0.12, 1), "glazing": "standard", "preferred_side": "front" if level == 0 else "any"})
        budget = footprint * rng.uniform(0.7, 0.85)
        used, n = 0.0, 0
        choices = ROOM_CHOICES[min(level, 1)]
        while used < budget and n < 7:
            rtype, low, high = rng.choice(choices)
            if rtype == "garage" and any(r["type"] == "garage" for r in rooms):
                continue
            area = round(min(rng.uniform(low, high), budget - used + 2), 1)
            if area < 1.5:
                break
            rid = f"{rtype}_{level}_{n}"
            rooms.append({"id": rid, "name": f"{rtype.replace('_', ' ').title()} {n}", "type": rtype, "floor": level,
                          "target_area": area, "glazing": rng.choice(["standard", "large", "none"]),
                          "preferred_side": rng.choice(["any", "any", "front", "rear", "left", "right"])})
            connections.append({"room_a": hall, "room_b": rid, "kind": "door"})
            used += area
            n += 1
    stairs = [{"from_floor": f, "to_floor": f + 1, "start_room": "hall" if f == 0 else f"landing_{f}", "arrival_room": f"landing_{f + 1}"}
              for f in range(floors - 1)]
    return {
        "understood": True, "project_name": "Random", "summary": "", "building_type": "detached_house", "style": "modern",
        "floors": floors, "floor_height": rng.choice([2.5, 2.7, 3.0]), "footprint_width": width, "footprint_depth": depth,
        "entrance_room": "hall", "rooms": rooms, "connections": connections, "stairs": stairs,
        "roof": {"type": rng.choice(["gable", "flat", "hip"]), "pitch": 30, "material": "slate"},
        "exterior": {"wall_material": "brick", "accent_material": None, "window_frame_material": "aluminium"},
        "site": {"driveway": rng.random() < 0.5, "patio": rng.random() < 0.7, "balcony_rooms": []}, "assumptions": [],
    }


def prepared(seed: int) -> dict:
    data = random_intent(random.Random(seed))
    if data["roof"]["type"] == "hip" and data["footprint_width"] < data["footprint_depth"]:
        data["roof"]["type"] = "gable"
    if data["roof"]["type"] == "flat":
        data["roof"]["pitch"] = 2
    return data


def test_most_realistic_intents_can_be_planned() -> None:
    planned = 0
    for seed in range(300):
        try:
            plan_building(DesignIntent.model_validate(prepared(seed)))
            planned += 1
        except PlanningError:
            pass
    assert planned >= 265, f"only {planned} of 300 random intents could be planned"


@pytest.mark.parametrize("seed", range(300))
def test_random_intent_plans_cleanly_or_fails_clearly(seed: int) -> None:
    data = prepared(seed)
    try:
        result = plan_building(DesignIntent.model_validate(data))
    except PlanningError:
        return  # a clear, user-facing refusal is acceptable
    assert result.report.error_count == 0, [i.message for i in result.report.issues if i.severity.value == "error"]
    assert not any("could not be connected" in n for n in result.notes)
    spec = result.specification
    types = {r.id: r.type for r in spec.rooms}
    routes = front_door_reachability(spec)
    assert set(routes) == set(types), "some rooms are only reachable from outside"
    for room_id, route in routes.items():
        assert_sensible_route(room_id, route, types)
