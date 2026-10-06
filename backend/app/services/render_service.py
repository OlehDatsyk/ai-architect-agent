"""Renders images from a built job with Blender.

Each render is renders/<render_id>.png plus <render_id>.json in the job folder. Requests are
checked here against the whitelists and the cameras the build created, then checked again by
the render runner inside Blender.
"""

import json
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import status
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.core.errors import AppError
from app.services.blender_service import RENDER_RUNNER, JobStore, blender_command

logger = logging.getLogger(__name__)

Quality = Literal["preview", "standard", "high"]
Resolution = Literal["1280x720", "1920x1080", "2560x1440"]
Engine = Literal["auto", "eevee", "cycles"]

# The engine "auto" resolves to, per Blender executable, for the life of the process: (engine, note).
_auto_engine: dict[str, tuple[str, str | None]] = {}
EEVEE_SLOWDOWN_LIMIT = 1.5  # with a real GPU, prefer EEVEE unless it is more than this much slower than Cycles
# OpenGL implementations that draw on the CPU: EEVEE works with them but is far slower than Cycles.
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swiftshader", "lavapipe", "microsoft basic render", "software rasterizer")


def software_renderer(name: str) -> bool:
    return any(marker in name.lower() for marker in SOFTWARE_RENDERERS)


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera: str = "Camera_Exterior_Front"
    preset: Literal["day", "evening"] = "day"
    quality: Quality = "preview"
    resolution: Resolution = "1280x720"
    engine: Engine | None = None  # None: the server's default (RENDER_DEFAULT_ENGINE)


@dataclass(frozen=True)
class RenderResult:
    render_id: str
    camera: str
    role: str | None
    preset: str
    quality: str
    engine: str
    width: int
    height: int
    duration_seconds: float
    note: str | None
    brightness: float = 0.0
    contrast: float = 0.0
    view_layer: str | None = None


class RenderService:
    def __init__(self, executable: Path, mode: str, jobs_dir: Path, timeout: float, default_engine: str,
                 probe_timeout: float, runner: Path = RENDER_RUNNER) -> None:
        self.executable, self.mode, self.runner = executable, mode, runner
        self.jobs = JobStore(jobs_dir)
        self.timeout, self.default_engine, self.probe_timeout = timeout, default_engine, probe_timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> "RenderService":
        if settings.blender_executable is None or not settings.blender_executable.is_file():
            raise AppError("blender_unavailable", "Blender connection unavailable. Set BLENDER_EXECUTABLE in .env and restart the backend.",
                           status.HTTP_503_SERVICE_UNAVAILABLE)
        return cls(settings.blender_executable, settings.blender_mode, settings.jobs_dir, settings.render_timeout_seconds,
                   settings.render_default_engine, settings.eevee_probe_timeout_seconds)

    def cameras(self, job_id: str) -> list[dict]:
        job = self.jobs.path(job_id)
        try:
            scene = json.loads((job / "scene.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError("job_not_found", "This job has no scene.", status.HTTP_404_NOT_FOUND) from exc
        return [{"name": c["name"], "role": c.get("tags", {}).get("role", "")} for c in scene.get("cameras", [])]

    def _probe(self, engine: str) -> dict | None:
        """The test render's report (seconds, GPU renderer) for `engine`, or None if it failed."""
        probe_dir = self.jobs.root / "_engine_probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        request = probe_dir / f"probe_{engine}.request.json"
        request.write_text(json.dumps({"probe": engine}), encoding="utf-8")
        result = probe_dir / f"probe_{engine}.json"
        result.unlink(missing_ok=True)
        try:
            done = subprocess.run(blender_command(self.executable, self.mode, self.runner, str(probe_dir), str(request)),
                                  capture_output=True, timeout=self.probe_timeout, check=False)
            data = json.loads(result.read_text(encoding="utf-8")) if done.returncode == 0 and result.is_file() else {}
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
            data = {}
        return data if data.get("ok") else None

    def auto_engine(self) -> tuple[str, str | None]:
        """EEVEE where it is practical (a GPU), otherwise Cycles, with a note saying why."""
        key = str(self.executable)
        if key not in _auto_engine:
            eevee = self._probe("eevee")
            renderer = (eevee or {}).get("gpu_renderer", "")
            cycles = self._probe("cycles") if eevee is not None and not software_renderer(renderer) else None
            if eevee is None:
                choice = ("cycles", "EEVEE is not available on this machine (it needs OpenGL), so Cycles was used.")
            elif software_renderer(renderer):
                choice = ("cycles", f"Cycles was used because this machine has no GPU: EEVEE would be drawn by the "
                                    f"software renderer {renderer.split(' (')[0]}, which is much slower.")
            elif cycles is not None and eevee["seconds"] > EEVEE_SLOWDOWN_LIMIT * cycles["seconds"]:
                choice = ("cycles", f"Cycles was used because it renders faster than EEVEE on this machine "
                                    f"({cycles['seconds']:.1f} s against {eevee['seconds']:.1f} s for a test scene).")
            else:
                choice = ("eevee", None)
            _auto_engine[key] = choice
            logger.info("Engine test on %s: EEVEE %s (GPU renderer %r), Cycles %s -> %s", key,
                        "failed" if eevee is None else f"{eevee['seconds']:.1f}s", renderer,
                        "not run" if cycles is None else f"{cycles['seconds']:.1f}s", choice[0])
        return _auto_engine[key]

    def render(self, job_id: str, request: RenderRequest) -> RenderResult:
        job = self.jobs.path(job_id)
        if not (job / "building.blend").is_file():
            raise AppError("job_not_found", "This job has no built model to render.", status.HTTP_404_NOT_FOUND)
        cameras = {c["name"] for c in self.cameras(job_id)}
        if request.camera not in cameras:
            raise AppError("unknown_camera", f"This design has no camera called {request.camera!r}.", status.HTTP_422_UNPROCESSABLE_CONTENT,
                           details={"cameras": sorted(cameras)})

        wanted = request.engine or self.default_engine
        note = None
        if wanted == "auto":
            engine, note = self.auto_engine()
        else:
            engine = wanted

        render_id = uuid.uuid4().hex
        request_file = job / "renders" / f"{render_id}.request.json"
        request_file.parent.mkdir(exist_ok=True)
        request_file.write_text(json.dumps({"render_id": render_id, "camera": request.camera, "preset": request.preset,
                                            "quality": request.quality, "resolution": request.resolution, "engine": engine}),
                                encoding="utf-8")
        started = time.perf_counter()
        log = job / "renders" / f"{render_id}.log"
        try:
            with log.open("w", encoding="utf-8") as out:
                completed = subprocess.run(blender_command(self.executable, self.mode, self.runner, str(job), str(request_file)),
                                           stdout=out, stderr=subprocess.STDOUT, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            hint = " EEVEE needs a working OpenGL context; try Cycles." if engine == "eevee" else " Try Preview quality or a lower resolution."
            raise AppError("render_timeout", f"The render did not finish within {self.timeout:.0f} seconds.{hint}",
                           status.HTTP_504_GATEWAY_TIMEOUT) from exc
        except OSError as exc:
            raise AppError("blender_unavailable", "Blender connection unavailable: Blender could not be started.",
                           status.HTTP_503_SERVICE_UNAVAILABLE) from exc

        try:
            result = json.loads((job / "renders" / f"{render_id}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result = {}
        if completed.returncode != 0 or result.get("status") != "ok":
            logger.error("Render %s failed: %s", render_id, result.get("traceback") or log.read_text(errors="replace")[-3000:])
            raise AppError("render_failed", f"Render failed: {result.get('message') or f'Blender exited with code {completed.returncode}.'}",
                           status.HTTP_502_BAD_GATEWAY)
        logger.info("Render %s: %s %s %s %dx%d in %.1fs", render_id, request.camera, engine, request.quality,
                    result["width"], result["height"], time.perf_counter() - started)
        return RenderResult(render_id=render_id, camera=request.camera, role=result.get("role"), preset=request.preset,
                            quality=request.quality, engine=engine, width=int(result["width"]), height=int(result["height"]),
                            duration_seconds=float(result["duration_seconds"]), note=note,
                            brightness=float(result.get("brightness", 0.0)), contrast=float(result.get("contrast", 0.0)),
                            view_layer=result.get("view_layer"))
