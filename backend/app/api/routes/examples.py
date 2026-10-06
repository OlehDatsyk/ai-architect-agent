"""Example prompts and specifications."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.services.example_repository import Example, ExampleRepository, ExampleSummary

router = APIRouter(prefix="/examples", tags=["examples"])


def get_example_repository(settings: Annotated[Settings, Depends(get_settings)]) -> ExampleRepository:
    return ExampleRepository(settings.examples_dir)


Repository = Annotated[ExampleRepository, Depends(get_example_repository)]


@router.get("", response_model=list[ExampleSummary])
def list_examples(repository: Repository) -> list[ExampleSummary]:
    return repository.list()


@router.get("/{example_id}", response_model=Example)
def get_example(example_id: str, repository: Repository) -> Example:
    return repository.get(example_id)
