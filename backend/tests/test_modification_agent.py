import json

import pytest
from fastapi.testclient import TestClient

from app.agents.modification_agent import OUTPUT_SCHEMA, SYSTEM_PROMPT, ModificationAgent, digest
from app.api.routes.designs import get_modification_factory
from app.core.errors import AppError
from app.main import create_app
from app.models.intent import DesignIntent
from app.modification.apply import realise
from tests.fake_claude import FakeClaudeClient, reply
from tests.intent_fixtures import british_house_intent

INTENT = DesignIntent.model_validate(british_house_intent())
CURRENT = realise(INTENT, []).specification
DONE_ITEM_18 = "Change the exterior to red brick and add another window to the master bedroom."


def change_set(*ops, understood=True, summary="Red brick walls and an extra master bedroom window."):
    return json.dumps({"understood": understood, "summary": summary, "assumptions": ["Red brick means a warm mid red."],
                       "operations": [{"op": op, "params": [{"key": k, "value": v} for k, v in params.items()]} for op, params in ops]})


RED_BRICK = ("set_exterior_material", {"surface": "wall", "material": "brick", "colour": "#A33A2A"})
MASTER_WINDOW = ("add_window", {"room_id": "master_bedroom", "side": "any", "size": "standard"})


async def test_definition_of_done_item_18() -> None:
    client = FakeClaudeClient([reply(change_set(RED_BRICK, MASTER_WINDOW))])
    result = await ModificationAgent(client).modify(INTENT, [], CURRENT, DONE_ITEM_18)

    assert result.report.error_count == 0 and result.attempts == 1
    assert "Exterior wall: brick -> brick (#A33A2A)." in result.changes
    assert any(c.startswith("Added a") and "Master Bedroom" in c for c in result.changes)
    assert len(result.changes) == 2  # nothing else changed
    assert [o.op for o in result.overrides] == ["set_exterior_material", "add_window"]
    call = client.calls[0]
    assert call["system"] == SYSTEM_PROMPT and call["schema"] is OUTPUT_SCHEMA
    assert "<current_design>" in call["messages"][0]["content"] and DONE_ITEM_18 in call["messages"][0]["content"]


async def test_wrong_room_id_is_sent_back_and_corrected() -> None:
    wrong = ("add_window", {"room_id": "main_bedroom"})
    client = FakeClaudeClient([reply(change_set(wrong)), reply(change_set(MASTER_WINDOW))])
    result = await ModificationAgent(client).modify(INTENT, [], CURRENT, "Add a window to the main bedroom")
    assert result.attempts == 2
    assert "There is no room 'main_bedroom'" in client.calls[1]["messages"][2]["content"]


async def test_missing_parameter_is_explained() -> None:
    client = FakeClaudeClient([reply(change_set(("set_room_area", {"room_id": "kitchen_dining"}))),
                               reply(change_set(("set_room_area", {"room_id": "kitchen_dining", "target_area": "24"})))])
    result = await ModificationAgent(client).modify(INTENT, [], CURRENT, "Make the kitchen bigger")
    assert "expected parameters: room_id, target_area" in client.calls[1]["messages"][2]["content"]
    assert any(c.startswith("Kitchen / Dining:") for c in result.changes)


async def test_area_change_blocked_by_the_layout_suggests_width() -> None:
    blocked = ("set_room_area", {"room_id": "living_room", "target_area": "18"})  # its depth is fixed by the garage
    width = next(r.width for r in CURRENT.rooms if r.id == "living_room") + 1
    client = FakeClaudeClient([reply(change_set(blocked)), reply(change_set(("set_room_width", {"room_id": "living_room", "width": f"{width:.2f}"})))])
    result = await ModificationAgent(client).modify(INTENT, [], CURRENT, "Make the living room bigger")
    assert "Use set_room_width" in client.calls[1]["messages"][2]["content"]
    assert result.attempts == 2 and any(c.startswith("Living Room:") for c in result.changes)


async def test_effect_that_cannot_happen_fails_safely() -> None:
    impossible = ("add_balcony", {"room_id": "landing"})  # the landing has no long exterior wall
    client = FakeClaudeClient([reply(change_set(impossible)), reply(change_set(impossible))])
    with pytest.raises(AppError) as caught:
        await ModificationAgent(client).modify(INTENT, [], CURRENT, "Add a balcony to the landing")
    assert caught.value.code == "modification_failed"


async def test_request_that_is_not_a_change() -> None:
    client = FakeClaudeClient([reply(change_set(understood=False, summary="That is a new building, not a change. Start a new design."))])
    with pytest.raises(AppError) as caught:
        await ModificationAgent(client).modify(INTENT, [], CURRENT, "Design me a castle")
    assert caught.value.code == "not_a_modification" and "new design" in caught.value.message


def test_digest_lists_ids_sides_and_windows() -> None:
    data = json.loads(digest(INTENT, CURRENT))
    rooms = {r["id"]: r for r in data["rooms"]}
    assert rooms["garage"]["side"] in ("left", "right") and rooms["garage"]["floor"] == 0
    assert data["windows"] and all("id" in w for w in data["windows"])


def test_modify_endpoint(make_settings) -> None:
    client_fake = FakeClaudeClient([reply(change_set(RED_BRICK, MASTER_WINDOW))])
    app = create_app(make_settings(anthropic_api_key="sk-ant-test"))
    app.dependency_overrides[get_modification_factory] = lambda: (lambda: ModificationAgent(client_fake))
    response = TestClient(app).post("/api/designs/modify", json={
        "request": DONE_ITEM_18, "intent": british_house_intent(), "overrides": [],
        "specification": json.loads(CURRENT.model_dump_json())})
    assert response.status_code == 200
    body = response.json()
    assert len(body["changes"]) == 2 and body["report"]["error_count"] == 0
    assert body["plans"] and body["overrides"][1]["op"] == "add_window"


def test_modify_needs_the_api_key(client) -> None:
    response = client.post("/api/designs/modify", json={"request": "Add a window", "intent": british_house_intent(),
                                                        "overrides": [], "specification": json.loads(CURRENT.model_dump_json())})
    assert response.status_code == 503 and response.json()["error"]["code"] == "anthropic_key_missing"
