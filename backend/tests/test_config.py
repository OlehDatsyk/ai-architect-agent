from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test ,")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_blank_values_become_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("BLENDER_EXECUTABLE", "  ")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.anthropic_api_key is None
    assert settings.blender_executable is None
    assert settings.anthropic_configured is False


def test_api_key_hidden_from_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.anthropic_configured is True
    assert "sk-ant-super-secret" not in repr(settings)
    assert "sk-ant-super-secret" not in settings.model_dump_json()


def test_env_file_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_MODEL=claude-test-model\nAPI_PORT=9001\n")
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert settings.anthropic_model == "claude-test-model"
    assert settings.api_port == 9001


def test_invalid_values_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "70000")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_blank_storage_directories_fall_back_to_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECTS_DIR", "")
    monkeypatch.setenv("JOBS_DIR", "  ")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.projects_dir.parts[-2:] == ("output", "projects")
    assert settings.jobs_dir.parts[-2:] == ("output", "jobs")
