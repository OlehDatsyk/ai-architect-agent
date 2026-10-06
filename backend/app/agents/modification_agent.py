"""Modification Agent: plain-English change request -> validated ChangeSet -> updated design.

    1. Claude sees a compact digest of the current design and returns a ChangeSet (structured output).
    2. Each operation is parsed into its typed model and checked against the design (IDs exist,
       materials suit the surface, and so on).
    3. Layout operations edit the design intent; finishing operations are appended to the overrides.
    4. The design is re-planned keeping the existing arrangement where possible, overrides are
       re-applied, the result is validated, and every operation's effect is verified.
    5. Problems at any step go back to Claude for one corrected ChangeSet; then it fails safely.
"""

import json
import logging
import re
from pathlib import Path

from anthropic import transform_schema
from fastapi import status
from pydantic import BaseModel, ValidationError

from app.agents.architect_agent import Usage
from app.core.errors import AppError
from app.models.building import BuildingSpecification
from app.models.intent import DesignIntent
from app.modification.apply import (
    ModificationError,
    Realised,
    apply_layout,
    check_operation,
    realise,
    verify_effects,
)
from app.modification.changeset import FINISH_OPS, ChangeSet, Op, Override, parse_operation
from app.modification.diff import describe_changes
from app.planner import PlanningError
from app.planner.anchor import anchor_from
from app.services.claude_service import StructuredClaudeClient, prepare_schema
from app.validation import ValidationReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "modification_system.md").read_text(encoding="utf-8")
OUTPUT_SCHEMA = prepare_schema(transform_schema(ChangeSet))
_TAG_PATTERN = re.compile(r"</?\s*(change_request|current_design)\s*>", re.IGNORECASE)


class ModificationResult(BaseModel):
    intent: DesignIntent
    overrides: list[Override]
    specification: BuildingSpecification
    change_set: ChangeSet
    changes: list[str]
    notes: list[str]
    report: ValidationReport
    attempts: int
    model: str
    usage: Usage


def digest(intent: DesignIntent, spec: BuildingSpecification) -> str:
    """What Claude needs to address the existing design, and nothing more."""
    anchor = anchor_from(spec)
    side_names = {0: "left", 1: "right"}
    rooms = []
    for r in spec.rooms:
        rooms.append({
            "id": r.id, "name": r.name, "type": r.type.value, "floor": r.floor, "area": round(r.area, 1),
            "width": round(r.width, 2), "depth": round(r.depth, 2),
            "side": side_names.get(anchor.sides.get(r.id)) if anchor else None,
            "from_front": round(r.y, 1), "floor_finish": r.floor_material.id.value if r.floor_material else None,
        })
    return json.dumps({
        "footprint": {"width": spec.building.width, "depth": spec.building.depth, "floors": len(spec.floors)},
        "rooms": rooms,
        "windows": [{"id": w.id, "room": w.room, "wall": w.wall.value, "width": w.width} for w in spec.windows],
        "exterior": {k: (getattr(spec.exterior, f"{k}_material").model_dump(mode="json") if getattr(spec.exterior, f"{k}_material") else None)
                     for k in ("wall", "accent", "trim", "window_frame", "door")},
        "roof": {"type": spec.roof.type.value, "pitch": spec.roof.pitch, "material": spec.roof.material.id.value},
        "balconies": [b.room for b in spec.balconies],
    }, separators=(",", ":"))


class ModificationAgent:
    def __init__(self, client: StructuredClaudeClient, max_attempts: int = 2) -> None:
        self._client = client
        self._max_attempts = max_attempts

    async def modify(self, intent: DesignIntent, overrides: list[Override], current: BuildingSpecification,
                     request: str) -> ModificationResult:
        text = _TAG_PATTERN.sub("", request).strip()
        messages: list[dict] = [{"role": "user", "content":
                                 f"<current_design>\n{digest(intent, current)}\n</current_design>\n\n<change_request>\n{text}\n</change_request>"}]
        usage = Usage()
        problems: list[str] = []
        for attempt in range(1, self._max_attempts + 1):
            reply = await self._client.generate(system=SYSTEM_PROMPT, messages=messages, schema=OUTPUT_SCHEMA)
            usage = usage.add(reply.usage)
            if reply.stop_reason == "refusal":
                raise AppError("modification_refused", "Claude declined this change request.", status.HTTP_422_UNPROCESSABLE_CONTENT)
            if reply.stop_reason == "max_tokens":
                raise AppError("claude_response_truncated", "Claude's reply was cut off. Try a smaller change.", status.HTTP_502_BAD_GATEWAY)
            try:
                change_set = ChangeSet.model_validate(json.loads(reply.text))
            except (json.JSONDecodeError, ValidationError) as exc:
                problems = [f"The reply did not match the ChangeSet format: {str(exc)[:300]}"]
            else:
                if not change_set.understood:
                    raise AppError("not_a_modification", change_set.summary or "Describe a change to this design.",
                                   status.HTTP_422_UNPROCESSABLE_CONTENT)
                if not change_set.operations:
                    problems = ["The change set contains no operations."]
                else:
                    outcome = self._apply(change_set, intent, overrides, current)
                    if isinstance(outcome, list):
                        problems = outcome
                    else:
                        new_intent, new_overrides, realised = outcome
                        changes = describe_changes(current, realised.specification)
                        logger.info("Modification applied in %d attempt(s): %d operation(s), %d change(s)",
                                    attempt, len(change_set.operations), len(changes))
                        return ModificationResult(
                            intent=new_intent, overrides=new_overrides, specification=realised.specification,
                            change_set=change_set, changes=changes, notes=realised.notes,
                            report=realised.report, attempts=attempt, model=reply.model, usage=usage)
            logger.warning("Modification attempt %d had problems: %s", attempt, "; ".join(problems[:5]))
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": "Your operations have these problems:\n" + "\n".join(f"- {p}" for p in problems)
                 + "\n\nReturn the complete corrected ChangeSet."},
            ]
        raise AppError("modification_failed", "The change could not be applied to this design: " + " ".join(problems[:3]),
                       status.HTTP_422_UNPROCESSABLE_CONTENT, details={"problems": problems})

    @staticmethod
    def _apply(change_set: ChangeSet, intent: DesignIntent, overrides: list[Override],
               current: BuildingSpecification) -> tuple[DesignIntent, list[Override], Realised] | list[str]:
        ops: list[Op] = []
        problems: list[str] = []
        for raw in change_set.operations:
            try:
                op = parse_operation(raw)
                check_operation(op, intent, current)
                ops.append(op)
            except ValueError as exc:  # includes ModificationError
                problems.append(str(exc))
        if problems:
            return problems
        new_intent, anchor = intent.model_copy(deep=True), anchor_from(current)
        new_overrides = list(overrides)
        try:
            for raw, op in zip(change_set.operations, ops):
                if raw.op in FINISH_OPS:
                    new_overrides.append(Override(op=raw.op, params={k: v for k, v in op.model_dump(mode="json").items() if v is not None}))
                else:
                    apply_layout(op, new_intent, anchor, current)
            realised = realise(new_intent, new_overrides, anchor)
        except (ModificationError, PlanningError) as exc:
            return [getattr(exc, "message", str(exc))]
        errors = [i.message for i in realised.report.issues if i.severity.value == "error"]
        errors += verify_effects(ops, realised.specification, current)
        return errors or (new_intent, new_overrides, realised)
