"""Saved projects: list, open, save, save again and delete."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.planner.preview import render_all
from app.projects.model import Project, ProjectData
from app.projects.repository import JsonProjectRepository, ProjectRepository
from app.schemas.designs import FloorPlanPreview
from app.services.specification_service import SpecificationSummary, summarise

router = APIRouter(prefix="/projects", tags=["projects"])


def get_repository(settings: Annotated[Settings, Depends(get_settings)]) -> ProjectRepository:
    return JsonProjectRepository(settings.projects_dir, settings.jobs_dir)


Repository = Annotated[ProjectRepository, Depends(get_repository)]


class ProjectListItem(BaseModel):
    id: str
    name: str
    version: int
    updated_at: datetime
    floors: int
    bedrooms: int
    changes: int
    thumbnail_url: str | None


class ProjectView(Project):
    """A project plus what is derived from it on the server: summary and floor-plan drawings."""

    summary: SpecificationSummary
    plans: list[FloorPlanPreview]


class ProjectUpdate(ProjectData):
    version: int = Field(ge=1, description="The version you opened; saving fails if someone saved since.")


def view(project: Project) -> ProjectView:
    return ProjectView(**project.model_dump(), summary=summarise(project.specification),
                       plans=[FloorPlanPreview(level=lvl, name=name, svg=svg) for lvl, name, svg in render_all(project.specification)])


@router.get("", response_model=list[ProjectListItem])
def list_projects(repository: Repository) -> list[ProjectListItem]:
    items = []
    for p in repository.list():
        summary = summarise(p.specification)
        thumbnail = next((r.image_url for r in reversed(p.renders) if r.available), None)
        items.append(ProjectListItem(id=p.id, name=p.name, version=p.version, updated_at=p.updated_at,
                                     floors=summary.floors, bedrooms=summary.bedrooms, changes=len(p.history),
                                     thumbnail_url=thumbnail))
    return items


@router.get("/{project_id}", response_model=ProjectView)
def get_project(project_id: str, repository: Repository) -> ProjectView:
    return view(repository.get(project_id))


@router.post("", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectData, repository: Repository) -> ProjectView:
    return view(repository.create(data))


@router.put("/{project_id}", response_model=ProjectView)
def update_project(project_id: str, data: ProjectUpdate, repository: Repository) -> ProjectView:
    return view(repository.update(project_id, ProjectData(**data.model_dump(exclude={"version"})), data.version))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, repository: Repository) -> Response:
    repository.delete(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
