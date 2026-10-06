"""Specification schema and validation endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Body

from app.models.building import BuildingSpecification
from app.schemas.specifications import ValidateResponse
from app.services.specification_service import summarise
from app.validation import validate_data

router = APIRouter(prefix="/specifications", tags=["specifications"])


@router.get("/schema")
def specification_schema() -> dict[str, Any]:
    """JSON Schema of BuildingSpecification (input form)."""
    return BuildingSpecification.model_json_schema()


@router.post("/validate", response_model=ValidateResponse)
def validate_specification(payload: Annotated[dict[str, Any], Body()]) -> ValidateResponse:
    """Validate a specification. Always 200 for a JSON object: the report says whether it passed."""
    result = validate_data(payload)
    return ValidateResponse(
        report=result.report,
        specification=result.specification,
        summary=summarise(result.specification) if result.specification else None,
    )
