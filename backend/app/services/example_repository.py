"""Read-only access to the example prompts and specifications in examples/.

Kept behind a small class so project storage (Phase 12) can follow the same pattern and
later move to a database without touching the routes.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import status
from pydantic import BaseModel

from app.core.errors import AppError

logger = logging.getLogger(__name__)

# Slugs only: no dots, slashes or other path characters can reach the filesystem.
EXAMPLE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ExampleSummary(BaseModel):
    id: str
    title: str
    prompt: str


class Example(ExampleSummary):
    specification: dict[str, Any]


class ExampleRepository:
    def __init__(self, root: Path) -> None:
        self._specs = (root / "specifications").resolve()
        self._prompts = (root / "prompts").resolve()

    def list(self) -> list[ExampleSummary]:
        if not self._specs.is_dir():
            logger.warning("Examples directory not found: %s", self._specs)
            return []
        summaries = []
        for path in sorted(self._specs.glob("*.json")):
            if EXAMPLE_ID_PATTERN.match(path.stem):
                example = self._load(path.stem)
                summaries.append(ExampleSummary(id=example.id, title=example.title, prompt=example.prompt))
        return summaries

    def get(self, example_id: str) -> Example:
        if not EXAMPLE_ID_PATTERN.match(example_id) or len(example_id) > 64:
            raise AppError("invalid_example_id", "Example IDs contain only lowercase letters, digits and hyphens.", status.HTTP_400_BAD_REQUEST)
        return self._load(example_id)

    def _load(self, example_id: str) -> Example:
        spec_path = (self._specs / f"{example_id}.json").resolve()
        if spec_path.parent != self._specs or not spec_path.is_file():
            raise AppError("example_not_found", f"There is no example called '{example_id}'.", status.HTTP_404_NOT_FOUND)
        try:
            specification = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Could not read example %s: %s", spec_path, exc)
            raise AppError("example_unreadable", f"Example '{example_id}' could not be read.", status.HTTP_500_INTERNAL_SERVER_ERROR) from exc
        prompt_path = self._prompts / f"{example_id}.txt"
        prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.is_file() else ""
        title = str(specification.get("project", {}).get("name", example_id))
        return Example(id=example_id, title=title, prompt=prompt, specification=specification)
