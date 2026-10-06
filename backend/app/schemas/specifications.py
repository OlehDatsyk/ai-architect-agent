"""API schemas for specification validation."""

from pydantic import BaseModel

from app.models.building import BuildingSpecification
from app.services.specification_service import SpecificationSummary
from app.validation.report import ValidationReport


class ValidateResponse(BaseModel):
    report: ValidationReport
    # The specification after safe automatic fixes; null if it could not be parsed.
    specification: BuildingSpecification | None
    summary: SpecificationSummary | None
