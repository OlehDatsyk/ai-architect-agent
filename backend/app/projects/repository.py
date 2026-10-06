"""Project storage behind a small interface, so a database can replace the JSON files later
without changing the API (implement ProjectRepository for PostgreSQL and swap the dependency)."""

import logging
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Protocol

from fastapi import status
from pydantic import ValidationError

from app.core.config import REPO_ROOT
from app.core.errors import AppError
from app.projects.model import BuildRef, Project, ProjectData, RenderRef, SavedBuild, SavedRender, now
from app.validation import validate_specification

logger = logging.getLogger(__name__)
PROJECT_ID = re.compile(r"^[0-9a-f]{32}$")


class ProjectRepository(Protocol):
    def list(self) -> list[Project]: ...
    def get(self, project_id: str) -> Project: ...
    def create(self, data: ProjectData) -> Project: ...
    def update(self, project_id: str, data: ProjectData, expected_version: int) -> Project: ...
    def delete(self, project_id: str) -> None: ...


def not_found() -> AppError:
    return AppError("project_not_found", "There is no such project.", status.HTTP_404_NOT_FOUND)


class JsonProjectRepository:
    """One JSON file per project. Writes are atomic (temporary file, then rename) and updates
    are checked against the stored version so concurrent saves cannot silently overwrite."""

    _lock = threading.Lock()  # serialises read-check-write within this process

    def __init__(self, root: Path, jobs_dir: Path) -> None:
        self.root = root
        self.jobs_dir = jobs_dir

    # ------------------------------------------------------------------ paths
    def _path(self, project_id: str) -> Path:
        if not PROJECT_ID.match(project_id):
            raise not_found()
        return self.root / f"{project_id}.json"

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    # ------------------------------------------------------------------ server-derived data
    def _complete(self, project_id: str, version: int, created_at, data: ProjectData) -> Project:
        result = validate_specification(data.specification)
        return Project(
            id=project_id, version=version, created_at=created_at, updated_at=now(),
            name=data.name, brief=data.brief, constraints=data.constraints, interpretation=data.interpretation,
            intent=data.intent, overrides=data.overrides,
            specification=result.specification or data.specification, report=result.report,
            notes=data.notes, history=data.history,
            build=self._build(data.build), renders=[self._render(r) for r in data.renders],
        )

    def _build(self, build: BuildRef | None) -> SavedBuild | None:
        if build is None:
            return None
        blend = self.jobs_dir / build.job_id / "building.blend"
        reference = build.model_dump(include=set(BuildRef.model_fields))  # stored projects carry derived fields too
        return SavedBuild(**reference, blend_path=self._relative(blend),
                          blend_url=f"/api/designs/jobs/{build.job_id}/building.blend", available=blend.is_file())

    def _render(self, render: RenderRef) -> SavedRender:
        image = self.jobs_dir / render.job_id / "renders" / f"{render.render_id}.png"
        reference = render.model_dump(include=set(RenderRef.model_fields))
        return SavedRender(**reference, image_path=self._relative(image),
                           image_url=f"/api/designs/jobs/{render.job_id}/renders/{render.render_id}.png",
                           available=image.is_file())

    # ------------------------------------------------------------------ storage
    def _read(self, path: Path) -> Project:
        try:
            project = Project.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            logger.error("Project file %s could not be read: %s", path, exc)
            raise AppError("project_unreadable", "This project file is damaged and could not be opened.",
                           status.HTTP_500_INTERNAL_SERVER_ERROR) from exc
        # Files may have been cleaned up since saving: report what is still there.
        return project.model_copy(update={
            "build": self._build(project.build) if project.build else None,
            "renders": [self._render(r) for r in project.renders],
        })

    def _write(self, project: Project) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(project.model_dump_json(indent=2))
            os.replace(tmp, self._path(project.id))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def list(self) -> list[Project]:
        projects = []
        for path in sorted(self.root.glob("*.json")) if self.root.is_dir() else []:
            if not PROJECT_ID.match(path.stem):
                continue
            try:
                projects.append(self._read(path))
            except AppError:
                continue  # a damaged file is logged, and does not hide the others
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def get(self, project_id: str) -> Project:
        path = self._path(project_id)
        if not path.is_file():
            raise not_found()
        return self._read(path)

    def create(self, data: ProjectData) -> Project:
        project = self._complete(uuid.uuid4().hex, 1, now(), data)
        with self._lock:
            self._write(project)
        logger.info("Saved new project %s '%s'", project.id, project.name)
        return project

    def update(self, project_id: str, data: ProjectData, expected_version: int) -> Project:
        with self._lock:
            current = self.get(project_id)
            if current.version != expected_version:
                raise AppError("project_changed", "This project was saved elsewhere since you opened it. Reopen it to see the latest version.",
                               status.HTTP_409_CONFLICT, details={"current_version": current.version})
            project = self._complete(project_id, current.version + 1, current.created_at, data)
            self._write(project)
        logger.info("Saved project %s '%s' version %d", project.id, project.name, project.version)
        return project

    def delete(self, project_id: str) -> None:
        path = self._path(project_id)
        with self._lock:
            if not path.is_file():
                raise not_found()
            path.unlink()
        logger.info("Deleted project %s", project_id)


__all__ = ["JsonProjectRepository", "ProjectRepository"]
