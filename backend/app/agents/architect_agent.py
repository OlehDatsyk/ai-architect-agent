"""Architect Agent: plain-English brief -> validated DesignIntent.

Flow for one interpretation:
  1. Send the system prompt, the brief and any fixed constraints, with the DesignIntent JSON
     schema as a structured-output format.
  2. Parse and validate the reply with Pydantic (types and every original constraint).
  3. Apply the user's advanced controls that can be set directly.
  4. Run deterministic intent checks.
  5. If there are errors, send them back and ask for a complete corrected design, up to
     max_attempts calls in total. Then fail safely with the outstanding issues.
"""

import json
import logging
import re
from pathlib import Path

from anthropic import transform_schema
from fastapi import status
from pydantic import BaseModel, ValidationError

from app.core.errors import AppError
from app.models.intent import DesignConstraints, DesignIntent, DesignRequest
from app.services.claude_service import StructuredClaudeClient, TokenUsage, prepare_schema
from app.validation.engine import schema_issue
from app.validation.intent import apply_constraints, validate_intent
from app.validation.report import Severity, ValidationIssue, ValidationReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "architect_system.md").read_text(encoding="utf-8")
# Unsupported constraints (min/max, patterns) move into descriptions; Pydantic still enforces them.
OUTPUT_SCHEMA = prepare_schema(transform_schema(DesignIntent))

_TAG_PATTERN = re.compile(r"</?\s*(building_request|constraints)\s*>", re.IGNORECASE)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0

    def add(self, usage: TokenUsage) -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + usage.input_tokens,
            output_tokens=self.output_tokens + usage.output_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + usage.cache_read_input_tokens,
        )


class InterpretationResult(BaseModel):
    intent: DesignIntent
    report: ValidationReport
    constraints_applied: list[str]
    attempts: int
    model: str
    usage: Usage
    completed_stages: list[str] = ["understanding_request"]


class ArchitectAgent:
    def __init__(self, client: StructuredClaudeClient, max_attempts: int = 2) -> None:
        self._client = client
        self._max_attempts = max_attempts

    async def interpret(self, request: DesignRequest) -> InterpretationResult:
        messages: list[dict] = [{"role": "user", "content": build_user_message(request)}]
        usage = Usage()
        outstanding: list[ValidationIssue] = []

        for attempt in range(1, self._max_attempts + 1):
            reply = await self._client.generate(system=SYSTEM_PROMPT, messages=messages, schema=OUTPUT_SCHEMA)
            usage = usage.add(reply.usage)

            if reply.stop_reason == "refusal":
                raise AppError("design_request_refused", "Claude declined to interpret this brief. Describe the building you want instead.", status.HTTP_422_UNPROCESSABLE_CONTENT)
            if reply.stop_reason == "max_tokens":
                raise AppError("claude_response_truncated", "The design was too large and Claude's reply was cut off. Try a smaller building or the Concept detail level.", status.HTTP_502_BAD_GATEWAY)

            intent, outstanding = parse_intent(reply.text)
            if intent is not None:
                if not intent.understood:
                    raise AppError("not_a_building_request", intent.summary or "Describe the building you want to create.", status.HTTP_422_UNPROCESSABLE_CONTENT)
                intent, notes = apply_constraints(intent, request.constraints)
                report = validate_intent(intent, request.constraints)
                if report.error_count == 0:
                    logger.info("Interpreted '%s' in %d attempt(s): %s", intent.project_name, attempt, report.status.value)
                    return InterpretationResult(
                        intent=intent, report=report, constraints_applied=notes,
                        attempts=attempt, model=reply.model, usage=usage,
                    )
                outstanding = [i for i in report.issues if i.severity is Severity.ERROR]

            logger.warning("Attempt %d produced %d problem(s): %s", attempt, len(outstanding), "; ".join(i.message for i in outstanding[:5]))
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": correction_message(outstanding, request.constraints)},
            ]

        raise AppError(
            "design_interpretation_failed",
            "Claude returned an invalid room layout. Try rephrasing or simplifying the brief.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"issues": [i.model_dump(mode="json") for i in outstanding]},
        )


def build_user_message(request: DesignRequest) -> str:
    # The brief is untrusted text: strip anything that could close or open our own tags.
    brief = _TAG_PATTERN.sub("", request.prompt).strip()
    return f"<building_request>\n{brief}\n</building_request>\n\n<constraints>\n{describe_constraints(request.constraints)}\n</constraints>"


def describe_constraints(c: DesignConstraints) -> str:
    lines = [f"Detail level: {c.detail_level}"]
    fixed = {
        "Building type": c.building_type and c.building_type.value,
        "Architectural style": c.style and c.style.value,
        "Floors": c.floors,
        "Footprint width (m)": c.width,
        "Footprint depth (m)": c.depth,
        "Approximate total height (m)": c.height,
        "Bedrooms": c.bedrooms,
        "Bathrooms including en-suites": c.bathrooms,
        "Garage": c.garage,
        "Roof type": None if c.roof == "automatic" else c.roof,
    }
    lines += [f"{label}: {value}" for label, value in fixed.items() if value is not None]
    if len(lines) == 1:
        lines.append("No other fixed requirements; decide from the brief.")
    return "\n".join(lines)


def parse_intent(text: str) -> tuple[DesignIntent | None, list[ValidationIssue]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, [ValidationIssue(severity=Severity.ERROR, code="invalid_json", message="The reply was not valid JSON.")]
    try:
        return DesignIntent.model_validate(data), []
    except ValidationError as exc:
        return None, [schema_issue(err) for err in exc.errors(include_url=False)]


def correction_message(issues: list[ValidationIssue], constraints: DesignConstraints) -> str:
    problems = "\n".join(f"- {issue.message}" for issue in issues[:30])
    return (
        "Your design has these problems:\n"
        f"{problems}\n\n"
        "Return the complete corrected design as one JSON object. Fix every problem above, keep "
        "everything else the same, and keep following these fixed requirements:\n"
        f"{describe_constraints(constraints)}"
    )
