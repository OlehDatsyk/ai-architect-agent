"""Planner behaviour on realistic intents: valid specifications with sensible circulation."""

from collections import deque

import pytest

from app.models import BuildingSpecification, DoorType, RoomType
from app.models.intent import DesignIntent
from app.planner import PlanningError, plan_building
from app.planner.preview import render_all
from app.validation import ValidationStatus
from tests.intent_fixtures import ALL_INTENTS, british_house_intent, luxury_intent, office_intent

PRIVATE = {RoomType.BATHROOM, RoomType.ENSUITE, RoomType.WC, RoomType.STORAGE, RoomType.GARAGE, RoomType.BEDROOM}
CHILD_TYPES = {RoomType.ENSUITE, RoomType.STORAGE, RoomType.WC}


def assert_sensible_route(room_id: str, route: list[str], types: dict) -> None:
    """Nobody walks through a bedroom, bathroom, store or garage to reach another room, except
    that a small room (en-suite, dressing room, store) may open off the one room it serves."""
    through = route[1:-1]
    if through and types[room_id] in CHILD_TYPES:
        through = through[:-1]  # its parent
    assert not {types[r] for r in through} & PRIVATE, f"{room_id} is reached through {route}"


def plan(data: dict):
    return plan_building(DesignIntent.model_validate(data))


def front_door_reachability(spec: BuildingSpecification) -> dict[str, list[str]]:
    """Shortest route from the front door to every room, through internal doors and stairs only."""
    front = next(d.connects_room_a for d in spec.doors if d.type is DoorType.FRONT)
    graph: dict[str, set[str]] = {r.id: set() for r in spec.rooms}
    for d in spec.doors:
        if not d.is_external and d.connects_room_b:
            graph[d.connects_room_a].add(d.connects_room_b)
            graph[d.connects_room_b].add(d.connects_room_a)
    halls = {r.floor: r.id for r in spec.rooms if r.type in (RoomType.ENTRANCE, RoomType.LANDING, RoomType.HALLWAY)}
    for s in spec.stairs:
        graph[halls[s.from_floor]].add(halls[s.to_floor])
        graph[halls[s.to_floor]].add(halls[s.from_floor])
    routes, queue = {front: [front]}, deque([front])
    while queue:
        current = queue.popleft()
        for nxt in graph[current]:
            if nxt not in routes:
                routes[nxt] = routes[current] + [nxt]
                queue.append(nxt)
    return routes


@pytest.mark.parametrize("slug", ALL_INTENTS)
def test_every_example_plans_without_errors(slug: str) -> None:
    result = plan(ALL_INTENTS[slug]())
    assert result.report.error_count == 0, [i.message for i in result.report.issues]


@pytest.mark.parametrize("slug", ALL_INTENTS)
def test_every_room_is_reached_from_the_front_door_without_walking_through_private_rooms(slug: str) -> None:
    spec = plan(ALL_INTENTS[slug]()).specification
    types = {r.id: r.type for r in spec.rooms}
    routes = front_door_reachability(spec)
    assert set(routes) == {r.id for r in spec.rooms}
    for room_id, route in routes.items():
        assert_sensible_route(room_id, route, types)


@pytest.mark.parametrize("slug", ALL_INTENTS)
def test_plans_are_deterministic(slug: str) -> None:
    first = plan(ALL_INTENTS[slug]()).specification.model_dump(exclude={"project": {"id", "created_at"}})
    second = plan(ALL_INTENTS[slug]()).specification.model_dump(exclude={"project": {"id", "created_at"}})
    assert first == second


def test_floors_tile_the_footprint_exactly() -> None:
    spec = plan(british_house_intent()).specification
    for floor in spec.floors:
        assert sum(r.area for r in spec.rooms_on_floor(floor.level)) == pytest.approx(spec.building.width * spec.building.depth, abs=0.05)


def test_stair_starts_in_hall_and_arrives_on_landing() -> None:
    result = plan(british_house_intent())
    spec = result.specification
    assert len(spec.stairs) == 1 and spec.stairs[0].from_floor == 0
    assert result.report.status is ValidationStatus.PASS  # includes stair-in-room and stair height checks


def test_ensuite_opens_only_from_its_bedroom() -> None:
    spec = plan(british_house_intent()).specification
    doors = [d for d in spec.doors if "ensuite" in (d.connects_room_a, d.connects_room_b)]
    assert {frozenset((d.connects_room_a, d.connects_room_b)) for d in doors} == {frozenset(("master_bedroom", "ensuite"))}


def test_open_plan_links_become_openings() -> None:
    spec = plan(luxury_intent()).specification
    pair = frozenset(("kitchen_dining", "living_room"))
    door = next(d for d in spec.doors if frozenset((d.connects_room_a, d.connects_room_b)) == pair)
    assert door.type is DoorType.OPENING and door.width >= 0.9


def test_garage_door_patio_door_and_balcony() -> None:
    spec = plan(luxury_intent()).specification
    garage_door = next(d for d in spec.doors if d.type is DoorType.GARAGE)
    assert garage_door.connects_room_a == "garage" and garage_door.width > 4
    patio = next(d for d in spec.doors if d.type is DoorType.PATIO_SLIDING and d.floor == 0)
    assert patio.position.y == spec.building.depth  # opens onto the rear garden
    assert [b.room for b in spec.balconies] == ["master_bedroom"]
    assert spec.environment.patio is not None and spec.environment.driveway is not None


def test_reception_is_entered_from_the_front() -> None:
    spec = plan(office_intent()).specification
    front = next(d for d in spec.doors if d.type is DoorType.FRONT)
    assert front.connects_room_a == "reception" and front.position.y == 0


def test_extra_corridors_are_merged_with_a_note() -> None:
    from tests.intent_fixtures import bungalow_intent

    result = plan(bungalow_intent())
    assert "corridor" not in {r.id for r in result.specification.rooms}
    assert any("Merged Bedroom Corridor" in n for n in result.notes)


def test_area_changes_are_reported() -> None:
    result = plan(luxury_intent())
    assert any("larger than" in n for n in result.notes)


def test_too_shallow_for_a_stair() -> None:
    data = british_house_intent()  # 81 m² per floor
    data["footprint_width"], data["footprint_depth"] = 19, 4.6  # same area, but too shallow for a 2.7 m stair
    with pytest.raises(PlanningError, match="Make the building deeper"):
        plan(data)


def test_too_many_rooms_for_the_footprint() -> None:
    data = british_house_intent()
    data["footprint_width"], data["footprint_depth"] = 12, 7.2
    data["rooms"] = [r for r in data["rooms"] if r["floor"] == 0 or r["id"] == "landing"]
    kept = {r["id"] for r in data["rooms"]}
    data["connections"] = [c for c in data["connections"] if {c["room_a"], c["room_b"]} <= kept]
    for i in range(8):  # eight bedrooms of at least 2.4 m depth cannot stack in two 7.2 m columns
        data["rooms"].append({"id": f"bedroom_{i}", "name": f"Bedroom {i}", "type": "bedroom", "floor": 1,
                              "target_area": 9, "glazing": "standard", "preferred_side": "any"})
        data["connections"].append({"room_a": "landing", "room_b": f"bedroom_{i}", "kind": "door"})
    with pytest.raises(PlanningError, match="do not fit"):
        plan(data)


def test_invalid_intent_is_rejected_before_planning() -> None:
    data = british_house_intent()
    data["stairs"] = []
    with pytest.raises(PlanningError, match="No stair connects"):
        plan(data)


def test_preview_renders_every_floor_and_escapes_names() -> None:
    data = british_house_intent()
    data["rooms"][1]["name"] = 'Living <script>alert("x")</script>'
    previews = render_all(plan(data).specification)
    assert [p[1] for p in previews] == ["Ground floor", "First floor"]
    assert all(svg.startswith("<svg") for _, _, svg in previews)
    assert "<script>" not in previews[0][2] and "&lt;script&gt;" in previews[0][2]
