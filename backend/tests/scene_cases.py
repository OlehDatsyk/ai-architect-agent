"""Specifications used by the scene tests: the five examples plus planner output."""

import json
from functools import cache

from app.models import BuildingSpecification
from app.models.intent import DesignIntent
from app.planner import PlanningError, plan_building
from tests.helpers import EXAMPLE_IDS, EXAMPLES_DIR
from tests.intent_fixtures import ALL_INTENTS
from tests.test_planner_random import prepared


@cache
def example_specs() -> dict[str, BuildingSpecification]:
    specs = {f"example:{slug}": BuildingSpecification.model_validate(
        json.loads((EXAMPLES_DIR / "specifications" / f"{slug}.json").read_text())) for slug in EXAMPLE_IDS}
    for slug, intent in ALL_INTENTS.items():
        specs[f"planned:{slug}"] = plan_building(DesignIntent.model_validate(intent())).specification
    return specs


@cache
def random_specs(count: int = 60) -> dict[str, BuildingSpecification]:
    specs = {}
    for seed in range(count):
        try:
            specs[f"random:{seed}"] = plan_building(DesignIntent.model_validate(prepared(seed))).specification
        except PlanningError:
            continue
    return specs


def all_specs() -> dict[str, BuildingSpecification]:
    return {**example_specs(), **random_specs()}


