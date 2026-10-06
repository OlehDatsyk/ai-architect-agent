"""Shared helpers for specification tests."""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from app.validation import ValidationReport, validate_data

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_IDS = ("british-family-house", "scandinavian-house", "modern-bungalow", "small-office", "luxury-house")


@cache
def _load(slug: str) -> dict[str, Any]:
    return json.loads((EXAMPLES_DIR / "specifications" / f"{slug}.json").read_text(encoding="utf-8"))


def example(slug: str = "british-family-house") -> dict[str, Any]:
    """A fresh, mutable copy of an example specification."""
    return copy.deepcopy(_load(slug))


def find(items: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    return next(item for item in items if item["id"] == item_id)


def report_for(data: dict[str, Any]) -> ValidationReport:
    return validate_data(data).report


def codes(report: ValidationReport) -> set[str]:
    return {issue.code for issue in report.issues}


def messages(report: ValidationReport) -> list[str]:
    return [issue.message for issue in report.issues]
