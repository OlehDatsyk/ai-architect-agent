"""Project data. The client sends ProjectData; the server adds identity, versioning, its own
validation report and every file path and URL, so a saved project cannot point at arbitrary files."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agents.architect_agent import InterpretationResult
from app.models.building import BuildingSpecification
from app.models.intent import DesignConstraints, DesignIntent
from app.modification.changeset import Override
from app.validation.report import ValidationReport

PROJECT_SCHEMA_VERSION = "1"
HexId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ModificationEntry(Strict):
    request: Annotated[str, StringConstraints(max_length=1000)]
    summary: Annotated[str, StringConstraints(max_length=400)] = ""
    changes: list[Annotated[str, StringConstraints(max_length=300)]] = Field(default_factory=list, max_length=100)
    assumptions: list[Annotated[str, StringConstraints(max_length=240)]] = Field(default_factory=list, max_length=20)


class CameraRef(Strict):
    name: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,59}$")]
    role: Annotated[str, StringConstraints(max_length=40)] = ""


class BuildRef(Strict):
    """What the client says it built. Paths and URLs are derived by the server from job_id."""

    job_id: HexId
    blender_version: Annotated[str, StringConstraints(max_length=40)] = ""
    object_count: int = Field(0, ge=0)
    cameras: list[CameraRef] = Field(default_factory=list, max_length=50)


class RenderRef(Strict):
    render_id: HexId
    job_id: HexId
    camera: Annotated[str, StringConstraints(max_length=60)]
    preset: Literal["day", "evening"]
    quality: Literal["preview", "standard", "high"]
    engine: Literal["eevee", "cycles"]
    width: int = Field(ge=1, le=10000)
    height: int = Field(ge=1, le=10000)
    note: Annotated[str, StringConstraints(max_length=300)] | None = None


class ProjectData(Strict):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    brief: Annotated[str, StringConstraints(max_length=4000)]
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)
    interpretation: InterpretationResult
    intent: DesignIntent
    overrides: list[Override] = Field(default_factory=list, max_length=200)
    specification: BuildingSpecification
    notes: list[Annotated[str, StringConstraints(max_length=400)]] = Field(default_factory=list, max_length=100)
    history: list[ModificationEntry] = Field(default_factory=list, max_length=200)
    build: BuildRef | None = None
    renders: list[RenderRef] = Field(default_factory=list, max_length=100)


class SavedBuild(BuildRef):
    blend_path: str
    blend_url: str
    available: bool


class SavedRender(RenderRef):
    image_path: str
    image_url: str
    available: bool


class Project(Strict):
    """A stored project. `report` is always the server's own validation of `specification`."""

    schema_version: Literal["1"] = PROJECT_SCHEMA_VERSION
    id: HexId
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    name: str
    brief: str
    constraints: DesignConstraints
    interpretation: InterpretationResult
    intent: DesignIntent
    overrides: list[Override]
    specification: BuildingSpecification
    report: ValidationReport
    notes: list[str]
    history: list[ModificationEntry]
    build: SavedBuild | None
    renders: list[SavedRender]


def now() -> datetime:
    return datetime.now(UTC)
