"""API schemas for design interpretation and planning."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agents.architect_agent import InterpretationResult
from app.models.building import BuildingSpecification
from app.models.intent import DesignIntent, DesignRequest
from app.modification.changeset import Override
from app.services.specification_service import SpecificationSummary
from app.validation.report import ValidationReport


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: DesignIntent


class FloorPlanPreview(BaseModel):
    level: int
    name: str
    svg: str


class PlanResponse(BaseModel):
    specification: BuildingSpecification
    report: ValidationReport
    summary: SpecificationSummary
    notes: list[str]
    plans: list[FloorPlanPreview]
    completed_stages: list[str] = ["planning_rooms", "creating_specification", "validating_design"]


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specification: BuildingSpecification


class CameraInfo(BaseModel):
    name: str
    role: str


class BuildResponse(BaseModel):
    job_id: str
    blend_url: str
    cameras: list[CameraInfo]
    blender_version: str
    object_count: int
    duration_seconds: float
    completed_stages: list[str]


class RenderResponse(BaseModel):
    render_id: str
    image_url: str
    camera: str
    role: str | None
    preset: str
    quality: str
    engine: str
    width: int
    height: int
    duration_seconds: float
    note: str | None
    completed_stages: list[str] = ["rendering"]


class ModifyRequest(BaseModel):
    """A change to an existing design. The client sends the design's current state back:
    its intent, the overrides applied so far, and the specification they produced."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request: Annotated[str, StringConstraints(min_length=3, max_length=1000)]
    intent: DesignIntent
    overrides: list[Override] = Field(default_factory=list, max_length=200)
    specification: BuildingSpecification


class ModifyResponse(BaseModel):
    intent: DesignIntent
    overrides: list[Override]
    specification: BuildingSpecification
    report: ValidationReport
    summary: SpecificationSummary
    plans: list[FloorPlanPreview]
    change_summary: str
    changes: list[str]
    assumptions: list[str]
    notes: list[str]
    attempts: int
    model: str
    completed_stages: list[str] = ["understanding_request", "planning_rooms", "creating_specification", "validating_design"]


__all__ = ["BuildRequest", "ModifyRequest", "ModifyResponse", "BuildResponse", "CameraInfo", "RenderResponse", "DesignRequest", "FloorPlanPreview", "InterpretationResult", "PlanRequest", "PlanResponse"]
