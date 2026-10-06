"""Live modification tests against the real Anthropic API (a few cents per run).

    RUN_LIVE_CLAUDE_TESTS=1 python -m pytest -m live -v -s tests/live/test_modification_live.py
"""

import os

import pytest

from app.agents.modification_agent import ModificationAgent
from app.api.routes.designs import build_architect_agent
from app.core.config import get_settings
from app.models.intent import DesignIntent
from app.modification.apply import realise
from tests.intent_fixtures import british_house_intent

settings = get_settings()
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_CLAUDE_TESTS") != "1" or not settings.anthropic_configured,
                       reason="Set RUN_LIVE_CLAUDE_TESTS=1 and ANTHROPIC_API_KEY to run live Claude tests."),
]

INTENT = DesignIntent.model_validate(british_house_intent())
CURRENT = realise(INTENT, []).specification


def agent() -> ModificationAgent:
    return ModificationAgent(build_architect_agent(settings)._client, max_attempts=settings.architect_max_attempts)


@pytest.mark.parametrize(("request_text", "expect"), [
    ("Change the exterior to red brick and add another window to the master bedroom.", ["Exterior wall", "Master Bedroom"]),
    ("Make the living room 1 metre wider.", ["Living Room"]),
    ("Add another window to the kitchen.", ["Kitchen"]),
    ("Change the roof to a hip roof.", ["Roof: gable"]),
    ("Make the exterior brick darker.", ["Exterior wall"]),
    ("Add a balcony above the garage.", ["balcony"]),
    ("Move the garage to the left side.", ["Garage"]),
])
async def test_brief_examples(request_text: str, expect: list[str]) -> None:
    result = await agent().modify(INTENT, [], CURRENT, request_text)
    print(f"\n{request_text}\n  ops: {[o.op for o in result.change_set.operations]}\n  " + "\n  ".join(result.changes))
    assert result.report.error_count == 0
    text = " ".join(result.changes)
    for fragment in expect:
        assert fragment.lower() in text.lower(), result.changes


async def test_claude_health_check_verifies_key_model_and_structured_outputs() -> None:
    """The same check as Verify in the System panel and GET /api/health/claude."""
    from app.api.routes.designs import build_claude_client

    result = await build_claude_client(settings).check()
    print(f"\nClaude check: {result.status}, structured outputs {result.structured_outputs}, {result.code or ''} {result.message or ''}")
    assert result.status == "verified" and result.structured_outputs == "ok", result.message
