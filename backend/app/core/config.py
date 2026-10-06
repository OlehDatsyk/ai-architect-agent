"""Typed application settings loaded from environment variables and the root .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/core/config.py -> repository root is three levels above "core".
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Architect Agent"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # SecretStr keeps the key out of reprs, logs and accidental serialisation.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_max_tokens: int = Field(default=8000, ge=1000, le=64000)
    anthropic_timeout_seconds: float = Field(default=120, ge=5, le=600)
    anthropic_max_retries: int = Field(default=2, ge=0, le=5)
    # Cache the (long, unchanging) system prompts. Turned off automatically if Anthropic rejects it.
    anthropic_prompt_caching: bool = True
    # Total Claude calls per interpretation: the first attempt plus corrective attempts.
    architect_max_attempts: int = Field(default=2, ge=1, le=4)

    blender_executable: Path | None = None
    # "binary": a Blender application. "python": a Python interpreter with the bpy module
    # (pip install bpy), used in CI. "auto": a file name starting with "python" means "python".
    blender_mode: Literal["auto", "binary", "python"] = "auto"
    blender_timeout_seconds: float = Field(default=300, ge=10, le=3600)
    render_timeout_seconds: float = Field(default=900, ge=10, le=7200)
    # "auto": EEVEE if a quick test render works on this machine, otherwise Cycles.
    render_default_engine: Literal["auto", "eevee", "cycles"] = "auto"
    eevee_probe_timeout_seconds: float = Field(default=45, ge=5, le=600)
    jobs_dir: Path = REPO_ROOT / "output" / "jobs"
    projects_dir: Path = REPO_ROOT / "output" / "projects"

    examples_dir: Path = REPO_ROOT / "examples"
    # Upper bound on request bodies. A large specification is well under 1 MB.
    max_request_bytes: int = Field(default=1_048_576, ge=1024, le=50_000_000)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("jobs_dir", "projects_dir", mode="before")
    @classmethod
    def _blank_dir_is_default(cls, value: object, info) -> object:
        # An empty JOBS_DIR= or PROJECTS_DIR= in .env means "the default", never the current directory.
        if isinstance(value, str) and not value.strip():
            return cls.model_fields[info.field_name].default
        return value

    @field_validator("anthropic_api_key", "blender_executable", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def anthropic_configured(self) -> bool:
        return (
            self.anthropic_api_key is not None
            and bool(self.anthropic_api_key.get_secret_value().strip())
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
