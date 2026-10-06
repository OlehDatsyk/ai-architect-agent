import os
import stat
from pathlib import Path

from fastapi.testclient import TestClient


def test_health_returns_ok_with_expected_shape(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "AI Architect Agent"
    assert body["environment"] == "test"
    assert body["version"]
    assert body["timestamp"]
    assert set(body["checks"]) == {"anthropic", "blender"}


def test_health_reports_anthropic_not_configured_without_key(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["checks"]["anthropic"]["configured"] is False


def test_health_reports_anthropic_configured_but_never_leaks_key(make_client) -> None:
    secret = "sk-ant-test-0123456789-should-never-appear"
    client = make_client(anthropic_api_key=secret)

    response = client.get("/api/health")

    assert response.json()["checks"]["anthropic"]["configured"] is True
    assert secret not in response.text


def test_whitespace_only_key_counts_as_not_configured(make_client) -> None:
    client = make_client(anthropic_api_key="   ")
    assert client.get("/api/health").json()["checks"]["anthropic"]["configured"] is False


def test_blender_not_configured(client: TestClient) -> None:
    blender = client.get("/api/health").json()["checks"]["blender"]
    assert blender["status"] == "not_configured"


def test_blender_missing_when_path_does_not_exist(make_client, tmp_path: Path) -> None:
    client = make_client(blender_executable=tmp_path / "no-such-blender")
    assert client.get("/api/health").json()["checks"]["blender"]["status"] == "missing"


def test_blender_found_when_path_is_executable(make_client, tmp_path: Path) -> None:
    fake_blender = tmp_path / "blender"
    fake_blender.write_text("#!/bin/sh\n")
    fake_blender.chmod(fake_blender.stat().st_mode | stat.S_IXUSR)
    if not os.access(fake_blender, os.X_OK):  # pragma: no cover - e.g. noexec tmp mounts
        return

    client = make_client(blender_executable=fake_blender)
    assert client.get("/api/health").json()["checks"]["blender"]["status"] == "found"


def test_blender_path_never_returned_in_response(make_client, tmp_path: Path) -> None:
    path = tmp_path / "private-dir" / "blender"
    client = make_client(blender_executable=path)
    assert str(path) not in client.get("/api/health").text



def test_claude_verification_is_cached_and_never_runs_from_the_main_health_check(make_settings, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.api.routes import health
    from app.main import create_app
    from app.services.claude_service import AnthropicStructuredClient, ClaudeCheck

    calls = []

    async def fake_check(self):
        calls.append(1)
        return ClaudeCheck("verified", self.model, 1_800_000_000.0, structured_outputs="ok")

    monkeypatch.setattr(AnthropicStructuredClient, "check", fake_check)
    monkeypatch.setattr(health, "_verifications", {})
    client = TestClient(create_app(make_settings(anthropic_api_key="sk-ant-test")))
    assert client.get("/api/health").json()["checks"]["anthropic"]["verification"]["status"] == "not_checked"
    assert client.get("/api/health/claude").json()["status"] == "verified"
    assert client.get("/api/health/claude").json()["status"] == "verified"
    assert len(calls) == 1  # the second call was served from the cache
    assert client.get("/api/health").json()["checks"]["anthropic"]["verification"]["status"] == "verified"
    client.get("/api/health/claude?refresh=true")
    assert len(calls) == 2
    assert "sk-ant-test" not in client.get("/api/health").text
