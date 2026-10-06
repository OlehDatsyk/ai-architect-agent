"""Validation entry points.

validate_data(raw)          -> parse untrusted JSON, then validate; schema errors become report issues.
validate_specification(spec) -> apply safe fixes, then run every rule.
"""

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.models.building import BuildingSpecification
from app.validation.context import ValidationContext
from app.validation.fixes import apply_fixes
from app.validation.report import Severity, ValidationIssue, ValidationReport
from app.validation.rules import ALL_RULES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationResult:
    report: ValidationReport
    # The corrected specification, or None when the input could not be parsed at all.
    specification: BuildingSpecification | None


def validate_specification(spec: BuildingSpecification) -> ValidationResult:
    fixed, fixes = apply_fixes(spec)
    ctx = ValidationContext.build(fixed)
    issues = [issue for rule in ALL_RULES for issue in rule(ctx)]
    report = ValidationReport.build(issues, fixes)
    logger.info(
        "Validated '%s': %s (%d errors, %d warnings, %d fixes)",
        fixed.project.name, report.status.value, report.error_count, report.warning_count, len(fixes),
    )
    return ValidationResult(report=report, specification=fixed)


def validate_data(data: Any) -> ValidationResult:
    try:
        spec = BuildingSpecification.model_validate(data)
    except ValidationError as exc:
        issues = [schema_issue(err) for err in exc.errors(include_url=False)]
        logger.info("Specification failed schema validation with %d error(s)", len(issues))
        return ValidationResult(report=ValidationReport.build(issues, []), specification=None)
    return validate_specification(spec)


def schema_issue(err: Any) -> ValidationIssue:
    location = format_location(err["loc"])
    return ValidationIssue(
        severity=Severity.ERROR,
        code="schema_invalid",
        message=f"{location or 'specification'}: {err['msg']}",
        location=location or None,
    )


def format_location(loc: tuple[Any, ...]) -> str:
    """('rooms', 3, 'width') -> 'rooms[3].width'"""
    parts: list[str] = []
    for part in loc:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        else:
            parts.append(("." if parts else "") + str(part))
    return "".join(parts)
