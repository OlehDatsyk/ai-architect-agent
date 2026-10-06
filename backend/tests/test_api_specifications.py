from fastapi.testclient import TestClient

from tests.helpers import example, find


def test_validate_valid_specification(client: TestClient) -> None:
    response = client.post("/api/specifications/validate", json=example())
    assert response.status_code == 200
    body = response.json()
    assert body["report"]["status"] == "PASS"
    assert body["summary"]["bedrooms"] == 3
    assert body["specification"]["project"]["name"] == "Contemporary British Family House"


def test_validate_returns_semantic_errors_as_report(client: TestClient) -> None:
    data = example()
    find(data["rooms"], "wc")["width"] = 2.2
    body = client.post("/api/specifications/validate", json=data).json()
    assert body["report"]["status"] == "ERROR"
    assert any(i["code"] == "room_overlap" for i in body["report"]["issues"])


def test_validate_schema_failure_returns_no_specification(client: TestClient) -> None:
    body = client.post("/api/specifications/validate", json={"rooms": []}).json()
    assert body["report"]["status"] == "ERROR"
    assert body["specification"] is None and body["summary"] is None


def test_validate_requires_json_object(client: TestClient) -> None:
    response = client.post("/api/specifications/validate", json=[1, 2, 3])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_oversized_body_is_rejected(make_client) -> None:
    client = make_client(max_request_bytes=2048)
    response = client.post("/api/specifications/validate", content=b"{" + b" " * 5000 + b"}",
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_oversized_chunked_body_is_rejected(make_client) -> None:
    client = make_client(max_request_bytes=2048)

    def chunks():
        yield b"{"
        for _ in range(10):
            yield b" " * 1000
        yield b"}"

    response = client.post("/api/specifications/validate", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_schema_endpoint(client: TestClient) -> None:
    schema = client.get("/api/specifications/schema").json()
    assert schema["title"] == "BuildingSpecification"
