"""Validation report types returned to the API and stored with projects."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidationIssue(BaseModel):
    severity: Severity
    code: str = Field(description="Stable machine-readable identifier of the rule that failed.")
    message: str
    element_ids: list[str] = Field(default_factory=list)
    location: str | None = Field(default=None, description="Path into the specification, for schema errors.")


class AppliedFix(BaseModel):
    code: str
    message: str
    element_ids: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    status: ValidationStatus
    error_count: int
    warning_count: int
    issues: list[ValidationIssue]
    fixes: list[AppliedFix]

    @classmethod
    def build(cls, issues: list[ValidationIssue], fixes: list[AppliedFix]) -> "ValidationReport":
        ordered = sorted(issues, key=lambda i: 0 if i.severity is Severity.ERROR else 1)
        errors = sum(1 for i in issues if i.severity is Severity.ERROR)
        warnings = len(issues) - errors
        status = ValidationStatus.ERROR if errors else ValidationStatus.WARNING if warnings else ValidationStatus.PASS
        return cls(status=status, error_count=errors, warning_count=warnings, issues=ordered, fixes=fixes)


def error(code: str, message: str, *element_ids: str) -> ValidationIssue:
    return ValidationIssue(severity=Severity.ERROR, code=code, message=message, element_ids=list(element_ids))


def warning(code: str, message: str, *element_ids: str) -> ValidationIssue:
    return ValidationIssue(severity=Severity.WARNING, code=code, message=message, element_ids=list(element_ids))
