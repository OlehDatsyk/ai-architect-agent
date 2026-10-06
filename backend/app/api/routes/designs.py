"""Design endpoints: brief -> Claude interpretation."""

from collections.abc import Callable
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from app.agents.architect_agent import ArchitectAgent
from app.agents.modification_agent import ModificationAgent
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.planner import plan_building
from app.planner.preview import render_all
from app.scene.compiler import compile_scene
from app.schemas.designs import (
    BuildRequest,
    BuildResponse,
    CameraInfo,
    DesignRequest,
    FloorPlanPreview,
    InterpretationResult,
    ModifyRequest,
    ModifyResponse,
    PlanRequest,
    PlanResponse,
    RenderResponse,
)
from app.services.blender_service import BlenderService, JobStore
from app.services.claude_service import AnthropicStructuredClient
from app.services.render_service import RenderRequest, RenderService
from app.services.specification_service import summarise
from app.validation import validate_specification

router = APIRouter(prefix="/designs", tags=["designs"])


AgentFactory = Callable[[], ArchitectAgent]


def build_claude_client(settings: Settings) -> AnthropicStructuredClient:
    """The one place the Anthropic client is configured. Anthropic's own error text reaches the
    browser only outside production."""
    if not settings.anthropic_configured or settings.anthropic_api_key is None:
        raise AppError(
            "anthropic_key_missing",
            "Anthropic API key is missing. Add ANTHROPIC_API_KEY to .env and restart the backend.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return AnthropicStructuredClient(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        timeout=settings.anthropic_timeout_seconds,
        max_retries=settings.anthropic_max_retries,
        prompt_caching=settings.anthropic_prompt_caching,
        expose_details=settings.app_env != "production",
    )


def build_architect_agent(settings: Settings) -> ArchitectAgent:
    if not settings.anthropic_configured or settings.anthropic_api_key is None:
        raise AppError(
            "anthropic_key_missing",
            "Anthropic API key is missing. Add ANTHROPIC_API_KEY to .env and restart the backend.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return ArchitectAgent(build_claude_client(settings), max_attempts=settings.architect_max_attempts)


def get_agent_factory(settings: Annotated[Settings, Depends(get_settings)]) -> AgentFactory:
    # A factory rather than the agent itself, so the request body is validated (422) before
    # configuration problems such as a missing API key (503) are reported.
    return partial(build_architect_agent, settings)


@router.post("/interpret", response_model=InterpretationResult)
async def interpret_design(
    request: DesignRequest,
    agent_factory: Annotated[AgentFactory, Depends(get_agent_factory)],
) -> InterpretationResult:
    """Interpret a brief into a validated DesignIntent for the user to review."""
    return await agent_factory().interpret(request)


@router.post("/plan", response_model=PlanResponse)
def plan_design(request: PlanRequest) -> PlanResponse:
    """Lay out a DesignIntent as a validated BuildingSpecification, with a floor-plan drawing per floor.

    Deterministic and free: no Claude call is made, so no API key is needed."""
    result = plan_building(request.intent)
    return PlanResponse(
        specification=result.specification,
        report=result.report,
        summary=summarise(result.specification),
        notes=result.notes,
        plans=[FloorPlanPreview(level=level, name=name, svg=svg) for level, name, svg in render_all(result.specification)],
    )


def get_blender_service(settings: Annotated[Settings, Depends(get_settings)]) -> Callable[[], BlenderService]:
    # A factory, so the request body is validated before Blender configuration is checked.
    return partial(BlenderService.from_settings, settings)


@router.post("/build", response_model=BuildResponse)
def build_design(
    request: BuildRequest,
    blender_factory: Annotated[Callable[[], BlenderService], Depends(get_blender_service)],
) -> BuildResponse:
    """Validate a specification, then build it in Blender and save a .blend file."""
    result = validate_specification(request.specification)
    if result.report.error_count or result.specification is None:
        raise AppError(
            "building_validation_failed", "Building validation failed, so nothing was sent to Blender.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"issues": [i.model_dump(mode="json") for i in result.report.issues if i.severity.value == "error"]},
        )
    scene = compile_scene(result.specification)
    built = blender_factory().build(scene)
    return BuildResponse(
        job_id=built.job_id,
        blend_url=f"/api/designs/jobs/{built.job_id}/building.blend",
        cameras=[CameraInfo(name=c.name, role=c.tags.get("role", "")) for c in scene.cameras],
        blender_version=built.blender_version,
        object_count=built.object_count,
        duration_seconds=built.duration_seconds,
        completed_stages=built.stages,
    )


@router.get("/jobs/{job_id}/building.blend")
def download_blend(job_id: str, settings: Annotated[Settings, Depends(get_settings)]) -> FileResponse:
    """Download the .blend file a build produced. Job IDs are random 128-bit hex strings."""
    blend = JobStore(settings.jobs_dir).path(job_id) / "building.blend"
    if not blend.is_file():
        raise AppError("job_not_found", "This job has no .blend file.", status.HTTP_404_NOT_FOUND)
    return FileResponse(blend, media_type="application/x-blender", filename="building.blend")


def get_render_service(settings: Annotated[Settings, Depends(get_settings)]) -> Callable[[], RenderService]:
    return partial(RenderService.from_settings, settings)


@router.post("/jobs/{job_id}/renders", response_model=RenderResponse)
def render_design(
    job_id: str,
    request: RenderRequest,
    render_factory: Annotated[Callable[[], RenderService], Depends(get_render_service)],
) -> RenderResponse:
    """Render one image of a built design. Every option is chosen from a fixed list."""
    rendered = render_factory().render(job_id, request)
    return RenderResponse(
        render_id=rendered.render_id,
        image_url=f"/api/designs/jobs/{job_id}/renders/{rendered.render_id}.png",
        camera=rendered.camera, role=rendered.role, preset=rendered.preset, quality=rendered.quality,
        engine=rendered.engine, width=rendered.width, height=rendered.height,
        duration_seconds=rendered.duration_seconds, note=rendered.note,
    )


@router.get("/jobs/{job_id}/renders/{render_id}.png")
def download_render(job_id: str, render_id: str, settings: Annotated[Settings, Depends(get_settings)]) -> FileResponse:
    if not (len(render_id) == 32 and all(c in "0123456789abcdef" for c in render_id)):
        raise AppError("render_not_found", "There is no such render.", status.HTTP_404_NOT_FOUND)
    image = JobStore(settings.jobs_dir).path(job_id) / "renders" / f"{render_id}.png"
    if not image.is_file():
        raise AppError("render_not_found", "There is no such render.", status.HTTP_404_NOT_FOUND)
    return FileResponse(image, media_type="image/png")


def build_modification_agent(settings: Settings) -> ModificationAgent:
    return ModificationAgent(build_claude_client(settings), max_attempts=settings.architect_max_attempts)


def get_modification_factory(settings: Annotated[Settings, Depends(get_settings)]) -> Callable[[], ModificationAgent]:
    return partial(build_modification_agent, settings)


@router.post("/modify", response_model=ModifyResponse)
async def modify_design(
    request: ModifyRequest,
    agent_factory: Annotated[Callable[[], ModificationAgent], Depends(get_modification_factory)],
) -> ModifyResponse:
    """Apply a plain-English change to an existing design, keeping everything else where it was."""
    result = await agent_factory().modify(request.intent, request.overrides, request.specification, request.request)
    return ModifyResponse(
        intent=result.intent, overrides=result.overrides, specification=result.specification, report=result.report,
        summary=summarise(result.specification),
        plans=[FloorPlanPreview(level=level, name=name, svg=svg) for level, name, svg in render_all(result.specification)],
        change_summary=result.change_set.summary, changes=result.changes, assumptions=result.change_set.assumptions,
        notes=result.notes, attempts=result.attempts, model=result.model,
    )
