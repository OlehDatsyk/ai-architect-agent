"""Runs Blender as a separate process to build a scene.

Each build is a job folder under output/jobs/<job_id>/ containing scene.json (input),
building.blend (output), result.json (what Blender built), progress.jsonl and blender.log.
Blender only ever runs this repository's runner script; the job contains data, not code.
"""

import json
import logging
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import status

from app.core.config import REPO_ROOT, Settings
from app.core.errors import AppError
from app.scene.model import SceneSpec

logger = logging.getLogger(__name__)

RUNNER = REPO_ROOT / "blender" / "scripts" / "runner.py"
RENDER_RUNNER = REPO_ROOT / "blender" / "scripts" / "render_runner.py"


def blender_command(executable: Path, mode: str, script: Path, *args: str) -> list[str]:
    """How to run one of our scripts: inside a Blender application, or with a Python that has bpy."""
    if mode == "auto":
        mode = "python" if executable.name.lower().startswith("python") else "binary"
    if mode == "python":
        return [str(executable), str(script), "--", *args]
    return [str(executable), "--background", "--factory-startup", "--python", str(script), "--", *args]
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
LOG_TAIL_LINES = 30


class JobStore:
    """Job folders under output/jobs/. IDs are validated so no path outside the store is ever used."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self) -> tuple[str, Path]:
        job_id = uuid.uuid4().hex
        path = self.root / job_id
        path.mkdir(parents=True)
        return job_id, path

    def path(self, job_id: str) -> Path:
        if not JOB_ID.match(job_id):
            raise AppError("job_not_found", "There is no such job.", status.HTTP_404_NOT_FOUND)
        path = (self.root / job_id).resolve()
        if path.parent != self.root.resolve() or not path.is_dir():
            raise AppError("job_not_found", "There is no such job.", status.HTTP_404_NOT_FOUND)
        return path


@dataclass(frozen=True)
class BuildResult:
    job_id: str
    blend_path: Path
    blender_version: str
    object_count: int
    duration_seconds: float
    stages: list[str]
    objects: list[dict]


class BlenderService:
    def __init__(self, executable: Path, mode: str, jobs_dir: Path, timeout: float, runner: Path = RUNNER) -> None:
        self.executable = executable
        self.mode = mode
        self.jobs = JobStore(jobs_dir)
        self.timeout = timeout
        self.runner = runner

    @classmethod
    def from_settings(cls, settings: Settings) -> "BlenderService":
        path = settings.blender_executable
        if path is None:
            raise AppError("blender_unavailable", "Blender connection unavailable. Set BLENDER_EXECUTABLE in .env and restart the backend.",
                           status.HTTP_503_SERVICE_UNAVAILABLE)
        if not path.is_file():
            raise AppError("blender_unavailable", "Blender connection unavailable: BLENDER_EXECUTABLE does not point to a file.",
                           status.HTTP_503_SERVICE_UNAVAILABLE)
        return cls(path, settings.blender_mode, settings.jobs_dir, settings.blender_timeout_seconds)

    def command(self, job_dir: Path) -> list[str]:
        return blender_command(self.executable, self.mode, self.runner, str(job_dir))

    def build(self, scene: SceneSpec) -> BuildResult:
        job_id, job = self.jobs.create()
        (job / "scene.json").write_text(scene.model_dump_json(), encoding="utf-8")
        logger.info("Blender job %s: %d elements for '%s'", job_id, len(scene.elements), scene.project_name)

        started = time.perf_counter()
        log_path = job / "blender.log"
        try:
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(self.command(job), stdout=log, stderr=subprocess.STDOUT,
                                           timeout=self.timeout, check=False, cwd=job)
        except subprocess.TimeoutExpired as exc:
            logger.error("Blender job %s timed out after %.0f s", job_id, self.timeout)
            raise AppError("blender_timeout", f"Blender did not finish within {self.timeout:.0f} seconds.",
                           status.HTTP_504_GATEWAY_TIMEOUT, details={"job_id": job_id}) from exc
        except OSError as exc:
            logger.error("Could not start Blender (%s): %s", self.executable, exc)
            raise AppError("blender_unavailable", "Blender connection unavailable: Blender could not be started.",
                           status.HTTP_503_SERVICE_UNAVAILABLE) from exc

        result = self._read_result(job)
        if completed.returncode != 0 or result.get("status") != "ok":
            message = result.get("message") or f"Blender exited with code {completed.returncode}."
            logger.error("Blender job %s failed: %s\n%s", job_id, message, _tail(log_path))
            raise AppError("blender_build_failed", f"Blender could not build the scene: {message}",
                           status.HTTP_502_BAD_GATEWAY, details={"job_id": job_id})
        blend = job / result.get("blend_file", "building.blend")
        if not blend.is_file():
            raise AppError("blender_build_failed", "Blender finished but did not save the .blend file.",
                           status.HTTP_502_BAD_GATEWAY, details={"job_id": job_id})

        objects = result.get("objects", [])
        duration = round(time.perf_counter() - started, 2)
        logger.info("Blender job %s done: %d objects in %.2f s (Blender %s)", job_id, len(objects), duration, result.get("blender_version"))
        return BuildResult(job_id=job_id, blend_path=blend, blender_version=str(result.get("blender_version", "unknown")),
                           object_count=len(objects), duration_seconds=duration, stages=list(result.get("stages", [])),
                           objects=objects)

    @staticmethod
    def _read_result(job: Path) -> dict:
        try:
            data = json.loads((job / "result.json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}


def _tail(path: Path) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_TAIL_LINES:])
    except OSError:
        return "(no log)"
