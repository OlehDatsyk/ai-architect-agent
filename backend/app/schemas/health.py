"""Response schemas for the health endpoint."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ClaudeVerification(BaseModel):
    """Whether Anthropic actually accepts requests, from the last (cached) check."""

    status: Literal["verified", "failed", "not_checked"]
    structured_outputs: Literal["ok", "failed", "not_checked"] = "not_checked"
    code: str | None = None
    message: str | None = None
    checked_at: datetime | None = None


class AnthropicCheck(BaseModel):
    configured: bool = Field(description="True when an API key is present. The key itself is never returned.")
    model: str
    verification: ClaudeVerification = Field(default_factory=lambda: ClaudeVerification(status="not_checked"))


class BlenderCheck(BaseModel):
    status: Literal["not_configured", "found", "missing"]
    detail: str


class HealthChecks(BaseModel):
    anthropic: AnthropicCheck
    blender: BlenderCheck


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    timestamp: datetime
    checks: HealthChecks
