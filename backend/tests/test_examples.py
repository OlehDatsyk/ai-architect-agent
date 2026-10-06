import pytest

from app.models import BuildingSpecification
from app.services.specification_service import summarise
from app.validation import ValidationStatus
from tests.helpers import EXAMPLE_IDS, EXAMPLES_DIR, example, report_for


def test_every_example_has_a_prompt_and_specification() -> None:
    specs = {p.stem for p in (EXAMPLES_DIR / "specifications").glob("*.json")}
    prompts = {p.stem for p in (EXAMPLES_DIR / "prompts").glob("*.txt")}
    assert specs == prompts == set(EXAMPLE_IDS)


@pytest.mark.parametrize("slug", EXAMPLE_IDS)
def test_example_passes_validation_without_fixes(slug: str) -> None:
    report = report_for(example(slug))
    assert report.status is ValidationStatus.PASS, [i.message for i in report.issues]
    assert report.fixes == []


@pytest.mark.parametrize("slug", EXAMPLE_IDS)
def test_example_round_trips(slug: str) -> None:
    spec = BuildingSpecification.model_validate(example(slug))
    assert spec.model_dump(mode="json") == example(slug)


@pytest.mark.parametrize(
    ("slug", "bedrooms", "bathrooms", "garage", "floors"),
    [
        ("british-family-house", 3, 2, "single", 2),
        ("scandinavian-house", 4, 1, "none", 2),
        ("modern-bungalow", 3, 1, "none", 1),
        ("small-office", 0, 0, "none", 2),
        ("luxury-house", 4, 2, "double", 2),
    ],
)
def test_examples_match_their_prompts(slug: str, bedrooms: int, bathrooms: int, garage: str, floors: int) -> None:
    summary = summarise(BuildingSpecification.model_validate(example(slug)))
    assert (summary.bedrooms, summary.bathrooms, summary.garage, summary.floors) == (bedrooms, bathrooms, garage, floors)


def test_examples_are_up_to_date_with_builder() -> None:
    """The committed JSON must match what scripts/build_example_specs.py produces."""
    from scripts.build_example_specs import EXAMPLES

    for slug, (build, _prompt) in EXAMPLES.items():
        assert build().model_dump(mode="json") == example(slug), f"Regenerate {slug}: python -m scripts.build_example_specs"
