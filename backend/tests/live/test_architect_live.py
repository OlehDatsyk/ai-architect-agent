"""Live tests against the real Anthropic API. They cost a few cents per run.

    RUN_LIVE_CLAUDE_TESTS=1 python -m pytest -m live -v

They are skipped unless RUN_LIVE_CLAUDE_TESTS=1 and ANTHROPIC_API_KEY is configured.
"""

import os
from collections import Counter

import pytest

from app.agents.architect_agent import ArchitectAgent
from app.core.config import get_settings
from app.models.intent import DesignConstraints, DesignRequest
from app.models.room import RoomType
from app.services.claude_service import AnthropicStructuredClient
from tests.helpers import EXAMPLES_DIR

settings = get_settings()

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_CLAUDE_TESTS") != "1" or not settings.anthropic_configured,
        reason="Set RUN_LIVE_CLAUDE_TESTS=1 and ANTHROPIC_API_KEY to run live Claude tests.",
    ),
]

# (example id, expected floors, expected bedrooms or None, expected garage or None)
CASES = [
    ("british-family-house", 2, 3, "single"),
    ("scandinavian-house", 2, 4, None),
    ("modern-bungalow", 1, 3, None),
    ("small-office", 2, None, None),
    ("luxury-house", 2, 4, "double"),
]


def agent() -> ArchitectAgent:
    assert settings.anthropic_api_key is not None
    client = AnthropicStructuredClient(
        api_key=settings.anthropic_api_key.get_secret_value(), model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens, timeout=settings.anthropic_timeout_seconds,
        max_retries=settings.anthropic_max_retries,
    )
    return ArchitectAgent(client, max_attempts=settings.architect_max_attempts)


@pytest.mark.parametrize(("slug", "floors", "bedrooms", "garage"), CASES)
async def test_example_prompt_is_interpreted(slug: str, floors: int, bedrooms: int | None, garage: str | None) -> None:
    prompt = (EXAMPLES_DIR / "prompts" / f"{slug}.txt").read_text(encoding="utf-8").strip()
    result = await agent().interpret(DesignRequest(prompt=prompt))

    intent = result.intent
    counts = Counter(r.type for r in intent.rooms)
    print(f"\n{slug}: {result.attempts} attempt(s), {result.report.status.value}, {len(intent.rooms)} rooms, "
          f"{result.usage.input_tokens} in / {result.usage.output_tokens} out tokens")
    assert result.report.error_count == 0
    assert intent.floors == floors
    if bedrooms is not None:
        assert counts[RoomType.BEDROOM] == bedrooms
    if garage == "double":
        assert any(r.type is RoomType.GARAGE and r.target_area >= 28 for r in intent.rooms)


async def test_constraints_override_the_brief() -> None:
    request = DesignRequest(
        prompt="A cosy three-bedroom family house with a garden.",
        constraints=DesignConstraints(bedrooms=4, roof="hip", style="traditional_british"),
    )
    result = await agent().interpret(request)
    assert sum(r.type is RoomType.BEDROOM for r in result.intent.rooms) == 4
    assert result.intent.roof.type == "hip"


async def test_non_building_brief_is_rejected() -> None:
    from app.core.errors import AppError

    with pytest.raises(AppError) as caught:
        await agent().interpret(DesignRequest(prompt="Write me a poem about the sea, please."))
    assert caught.value.code in ("not_a_building_request", "design_request_refused")
