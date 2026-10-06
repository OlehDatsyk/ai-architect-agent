from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import create_app


def test_request_id_generated_when_absent(client: TestClient) -> None:
    response = client.get("/api/health")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32 and request_id.isalnum()


def test_safe_incoming_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_unsafe_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "bad id\nwith-injection"})
    assert response.headers["X-Request-ID"] != "bad id\nwith-injection"
    assert response.headers["X-Request-ID"].isalnum()


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_app_error_uses_error_envelope(make_settings, make_client) -> None:
    app = create_app(make_settings())

    @app.get("/api/_test/app-error")
    def _raise() -> None:
        raise AppError("anthropic_key_missing", "Anthropic API key is missing.", status_code=503)

    response = make_client(app=app).get("/api/_test/app-error")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "anthropic_key_missing"
    assert response.json()["error"]["message"] == "Anthropic API key is missing."


def test_unhandled_exception_returns_safe_500(make_settings, make_client) -> None:
    app = create_app(make_settings())

    @app.get("/api/_test/crash")
    def _crash() -> None:
        raise RuntimeError("internal detail that must not reach the client")

    response = make_client(app=app, raise_server_exceptions=False).get("/api/_test/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "internal detail" not in response.text


def test_request_validation_error_uses_envelope(make_settings, make_client) -> None:
    app = create_app(make_settings())

    @app.get("/api/_test/needs-int")
    def _needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    response = make_client(app=app).get("/api/_test/needs-int", params={"n": "abc"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["fields"][0]["location"] == "query.n"


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers
