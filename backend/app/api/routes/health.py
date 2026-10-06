"""Health endpoint: reports that the API is up plus real configuration checks."""

import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import __version__
from app.core.config import Settings, get_settings
from app.schemas.health import AnthropicCheck, BlenderCheck, ClaudeVerification, HealthChecks, HealthResponse

router = APIRouter(tags=["health"])


def check_blender(settings: Settings) -> BlenderCheck:
    path = settings.blender_executable
    if path is None:
        return BlenderCheck(status="not_configured", detail="BLENDER_EXECUTABLE is not set.")
    if path.is_file() and (os.access(path, os.X_OK) or path.suffix.lower() == ".exe"):
        return BlenderCheck(status="found", detail="Blender executable found.")
    return BlenderCheck(status="missing", detail="BLENDER_EXECUTABLE does not point to an executable file.")


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
        checks=HealthChecks(
            anthropic=AnthropicCheck(
                configured=settings.anthropic_configured,
                model=settings.anthropic_model,
                verification=cached_verification(settings),  # never calls Anthropic
            ),
            blender=check_blender(settings),
        ),
    )


# Claude verification results, per model, for VERIFY_TTL seconds: checking costs a (tiny) API call.
VERIFY_TTL = 600
_verifications: dict[str, ClaudeVerification] = {}


def cached_verification(settings: Settings) -> ClaudeVerification:
    result = _verifications.get(settings.anthropic_model)
    if result and result.checked_at and (datetime.now(UTC) - result.checked_at).total_seconds() < VERIFY_TTL:
        return result
    return ClaudeVerification(status="not_checked")


@router.get("/health/claude", response_model=ClaudeVerification)
async def verify_claude(settings: Annotated[Settings, Depends(get_settings)],
                        refresh: Annotated[bool, Query(description="Check again even if a recent result exists.")] = False) -> ClaudeVerification:
    """Send a tiny text request and a tiny structured-output request to Anthropic. The result is
    cached for 10 minutes, so this is cheap to call; the API key is configured, not proven, until it passes."""
    from app.api.routes.designs import build_claude_client  # the one place the client is configured

    cached = cached_verification(settings)
    if cached.status != "not_checked" and not refresh:
        return cached
    check = await build_claude_client(settings).check()
    result = ClaudeVerification(status=check.status, structured_outputs=check.structured_outputs, code=check.code,  # type: ignore[arg-type]
                                message=check.message, checked_at=datetime.fromtimestamp(check.checked_at, UTC))
    _verifications[settings.anthropic_model] = result
    return result
