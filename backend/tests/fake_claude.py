"""A scripted StructuredClaudeClient for tests: returns queued replies and records every call."""

from dataclasses import dataclass, field
from typing import Any

from app.services.claude_service import StructuredReply, TokenUsage


@dataclass
class FakeClaudeClient:
    replies: list[StructuredReply]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def generate(self, *, system: str, messages: list[dict[str, Any]], schema: dict[str, Any]) -> StructuredReply:
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "schema": schema})
        if not self.replies:
            raise AssertionError("FakeClaudeClient ran out of scripted replies")
        return self.replies.pop(0)


def reply(text: str, stop_reason: str = "end_turn") -> StructuredReply:
    return StructuredReply(text=text, stop_reason=stop_reason, model="claude-sonnet-5-5",
                           usage=TokenUsage(input_tokens=3000, output_tokens=1500, cache_read_input_tokens=2500))
