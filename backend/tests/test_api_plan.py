import pytest
from fastapi.testclient import TestClient

from tests.intent_fixtures import ALL_INTENTS, british_house_intent


@pytest.mark.parametrize("slug", ALL_INTENTS)
def test_plan_endpoint_returns_valid_specification_and_drawings(client: TestClient, slug: str) -> None:
    response = client.post("/api/designs/plan", json={"intent": ALL_INTENTS[slug]()})
    assert response.status_code == 200
    body = response.json()
    assert body["report"]["error_count"] == 0
    assert len(body["plans"]) == body["summary"]["floors"]
    assert all(p["svg"].startswith("<svg") for p in body["plans"])
    assert body["completed_stages"] == ["planning_rooms", "creating_specification", "validating_design"]


def test_plan_works_without_an_api_key(client: TestClient) -> None:
    # The client fixture has no Anthropic key configured.
    assert client.post("/api/designs/plan", json={"intent": british_house_intent()}).status_code == 200


def test_plan_output_validates_again_through_the_validation_endpoint(client: TestClient) -> None:
    spec = client.post("/api/designs/plan", json={"intent": british_house_intent()}).json()["specification"]
    assert client.post("/api/specifications/validate", json=spec).json()["report"]["status"] == "PASS"


def test_unplannable_intent_is_a_clear_422(client: TestClient) -> None:
    data = british_house_intent()
    data["footprint_width"], data["footprint_depth"] = 19, 4.6
    response = client.post("/api/designs/plan", json={"intent": data})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "planning_failed"
    assert "deeper" in response.json()["error"]["message"]


def test_malformed_intent_is_rejected(client: TestClient) -> None:
    response = client.post("/api/designs/plan", json={"intent": {"rooms": []}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
