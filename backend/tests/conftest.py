from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

SettingsFactory = Callable[..., Settings]


@pytest.fixture
def make_settings() -> SettingsFactory:
    """Build Settings in isolation from the developer's real .env and shell environment."""

    def _make(**overrides: object) -> Settings:
        base: dict[str, object] = {"app_env": "test", "anthropic_api_key": None, "blender_executable": None}
        base.update(overrides)
        return Settings(_env_file=None, **base)  # type: ignore[call-arg]

    return _make


@pytest.fixture
def make_client(make_settings: SettingsFactory) -> Callable[..., TestClient]:
    def _make(app: FastAPI | None = None, raise_server_exceptions: bool = True, **overrides: object) -> TestClient:
        app = app or create_app(make_settings(**overrides))
        return TestClient(app, raise_server_exceptions=raise_server_exceptions)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
