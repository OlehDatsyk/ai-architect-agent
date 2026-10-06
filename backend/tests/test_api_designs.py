from fastapi.testclient import TestClient

from app.agents.architect_agent import ArchitectAgent
from app.api.routes.designs import get_agent_factory
from app.main import create_app
from tests.fake_claude import FakeClaudeClient, reply
from tests.intent_fixtures import as_reply_text, british_house_intent

BRIEF = {"prompt": "Create a modern two-storey British house with three bedrooms and a single garage."}


def client_with_fake(make_settings, replies) -> tuple[TestClient, FakeClaudeClient]:
    fake = FakeClaudeClient(replies)
    app = create_app(make_settings(anthropic_api_key="sk-ant-test"))
    app.dependency_overrides[get_agent_factory] = lambda: (lambda: ArchitectAgent(fake, max_attempts=2))
    return TestClient(app), fake


def test_interpret_returns_intent_and_report(make_settings) -> None:
    client, fake = client_with_fake(make_settings, [reply(as_reply_text(british_house_intent()))])
    response = client.post("/api/designs/interpret", json=BRIEF | {"constraints": {"detail_level": "concept"}})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["floors"] == 2
    assert body["report"]["status"] in ("PASS", "WARNING")
    assert body["completed_stages"] == ["understanding_request"]
    assert "Detail level: concept" in fake.calls[0]["messages"][0]["content"]


def test_missing_api_key_is_a_clear_503(client: TestClient) -> None:
    response = client.post("/api/designs/interpret", json=BRIEF)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "anthropic_key_missing"
    assert "ANTHROPIC_API_KEY" in response.json()["error"]["message"]


def test_failed_interpretation_includes_issues(make_settings) -> None:
    broken = british_house_intent()
    broken["stairs"] = []
    client, _ = client_with_fake(make_settings, [reply(as_reply_text(broken)), reply(as_reply_text(broken))])
    response = client.post("/api/designs/interpret", json=BRIEF)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "design_interpretation_failed"
    assert any(i["code"] == "floors_not_connected" for i in error["issues"])


def test_brief_length_limits(client: TestClient) -> None:
    assert client.post("/api/designs/interpret", json={"prompt": "house"}).status_code == 422
    assert client.post("/api/designs/interpret", json={"prompt": "x" * 4001}).status_code == 422


def test_invalid_constraints_rejected(client: TestClient) -> None:
    response = client.post("/api/designs/interpret", json=BRIEF | {"constraints": {"floors": 0}})
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["location"] == "body.constraints.floors"


def test_unknown_constraint_rejected(client: TestClient) -> None:
    response = client.post("/api/designs/interpret", json=BRIEF | {"constraints": {"pool": True}})
    assert response.status_code == 422
