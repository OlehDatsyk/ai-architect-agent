"""Deterministic validation engine for BuildingSpecification. No AI is involved here."""

from app.validation.engine import ValidationResult, validate_data, validate_specification
from app.validation.report import AppliedFix, Severity, ValidationIssue, ValidationReport, ValidationStatus

__all__ = [
    "AppliedFix", "Severity", "ValidationIssue", "ValidationReport", "ValidationResult", "ValidationStatus",
    "validate_data", "validate_specification",
]
