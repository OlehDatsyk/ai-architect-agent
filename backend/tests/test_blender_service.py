"""Job orchestration with stand-in executables that behave like Blender succeeding, failing,
crashing or hanging. No real Blender needed."""

import json
import stat
import sys
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.models import BuildingSpecification
from app.scene.compiler import compile_scene
from app.services.blender_service import BlenderService, JobStore
from tests.helpers import example

SCENE = compile_scene(BuildingSpecification.model_validate(example()))

OK = """
job = Path(sys.argv[-1]); scene = json.loads((job / "scene.json").read_text())
(job / "building.blend").write_bytes(b"BLENDER-v502")
(job / "result.json").write_text(json.dumps({"status": "ok", "blender_version": "5.2.2 LTS", "blend_file": "building.blend",
    "stages": ["preparing_scene", "generating_geometry"], "objects": [{"name": e["name"]} for e in scene["elements"]]}))
"""
FAIL = """
job = Path(sys.argv[-1])
(job / "result.json").write_text(json.dumps({"status": "error", "error": "build_failed", "message": "bad things"}))
print("Traceback: something deep inside Blender"); sys.exit(1)
"""
CRASH = "print('Segmentation fault'); sys.exit(139)"
HANG = "import time; time.sleep(30)"
NO_BLEND = """
job = Path(sys.argv[-1])
(job / "result.json").write_text(json.dumps({"status": "ok", "blend_file": "building.blend", "objects": []}))
"""


def fake_blender(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_blender"
    script.write_text(f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def service(tmp_path: Path, body: str, timeout: float = 20) -> BlenderService:
    return BlenderService(fake_blender(tmp_path, body), "binary", tmp_path / "jobs", timeout)


def test_successful_build(tmp_path: Path) -> None:
    result = service(tmp_path, OK).build(SCENE)
    assert result.object_count == len(SCENE.elements)
    assert result.blender_version == "5.2.2 LTS"
    assert result.stages == ["preparing_scene", "generating_geometry"]
    job = tmp_path / "jobs" / result.job_id
    assert result.blend_path == job / "building.blend"
    assert json.loads((job / "scene.json").read_text())["project_name"] == SCENE.project_name


def test_command_for_blender_binary_and_bpy_python(tmp_path: Path) -> None:
    job = tmp_path / "job"
    binary = BlenderService(Path("/opt/blender/blender"), "auto", tmp_path, 10).command(job)
    assert binary[:4] == ["/opt/blender/blender", "--background", "--factory-startup", "--python"]
    assert binary[-2:] == ["--", str(job)]
    python = BlenderService(Path("/venv/bin/python3.13"), "auto", tmp_path, 10).command(job)
    assert python[0] == "/venv/bin/python3.13" and python[1].endswith("runner.py") and python[-2:] == ["--", str(job)]


@pytest.mark.parametrize(("body", "code", "text"), [
    (FAIL, "blender_build_failed", "bad things"),
    (CRASH, "blender_build_failed", "exited with code 139"),
    (NO_BLEND, "blender_build_failed", "did not save"),
])
def test_failures_are_reported_clearly(tmp_path: Path, body: str, code: str, text: str, caplog) -> None:
    with pytest.raises(AppError) as caught:
        service(tmp_path, body).build(SCENE)
    assert caught.value.code == code and text in caught.value.message
    assert "job_id" in caught.value.details


def test_failure_details_go_to_the_log_not_the_user(tmp_path: Path, caplog) -> None:
    with pytest.raises(AppError) as caught:
        service(tmp_path, FAIL).build(SCENE)
    assert "Traceback" not in caught.value.message
    assert "Traceback: something deep inside Blender" in caplog.text


def test_timeout(tmp_path: Path) -> None:
    with pytest.raises(AppError) as caught:
        service(tmp_path, HANG, timeout=1).build(SCENE)
    assert caught.value.code == "blender_timeout"


def test_executable_that_cannot_start(tmp_path: Path) -> None:
    broken = tmp_path / "not_executable"
    broken.write_text("nope")
    with pytest.raises(AppError) as caught:
        BlenderService(broken, "binary", tmp_path / "jobs", 10).build(SCENE)
    assert caught.value.code == "blender_unavailable"


@pytest.mark.parametrize("job_id", ["../../etc", "ABCDEF", "0" * 31, "0" * 32])
def test_job_store_rejects_unknown_or_unsafe_ids(tmp_path: Path, job_id: str) -> None:
    with pytest.raises(AppError) as caught:
        JobStore(tmp_path).path(job_id)
    assert caught.value.code == "job_not_found"
