"""A complete, realistic project payload: interpreted, planned and (optionally) built."""

import json

from app.models.intent import DesignIntent
from app.modification.apply import realise
from tests.intent_fixtures import british_house_intent

BRIEF = "Create a modern two-storey British house with three bedrooms, two bathrooms and a single garage."
_INTENT = DesignIntent.model_validate(british_house_intent())
_SPEC = json.loads(realise(_INTENT, []).specification.model_dump_json())


def interpretation() -> dict:
    return {"intent": british_house_intent(), "report": {"status": "PASS", "error_count": 0, "warning_count": 0, "issues": [], "fixes": []},
            "constraints_applied": [], "attempts": 1, "model": "claude-sonnet-5-5",
            "usage": {"input_tokens": 3000, "output_tokens": 1500, "cache_read_input_tokens": 0},
            "completed_stages": ["understanding_request"]}


def project_data(**changes) -> dict:
    data = {"name": "Family house", "brief": BRIEF, "constraints": {}, "interpretation": interpretation(),
            "intent": british_house_intent(), "overrides": [], "specification": json.loads(json.dumps(_SPEC)),
            "notes": [], "history": [], "build": None, "renders": []}
    data.update(changes)
    return data
