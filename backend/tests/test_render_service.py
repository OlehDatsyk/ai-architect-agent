"""Render jobs with stand-in executables: success, failure, timeouts and the EEVEE fallback."""

import json
import stat
import sys
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services import render_service
from app.services.render_service import RenderRequest, RenderService

FAKE = """#!{python}
import json, sys, time
from pathlib import Path
args = sys.argv[sys.argv.index("--") + 1:]
job, request = Path(args[0]), json.loads(Path(args[1]).read_text())
if "probe" in request:
    engine = request["probe"]
    seconds, renderer = {probe}[engine]
    if seconds == "fail":
        sys.exit(3)
    if seconds == "hang":
        time.sleep(30)
    (job / f"probe_{{engine}}.json").write_text(json.dumps({{"engine": engine, "ok": True, "seconds": seconds, "gpu_renderer": renderer}}))
    sys.exit(0)
{render}
rid = request["render_id"]
(job / "renders" / f"{{rid}}.png").write_bytes(b"\\x89PNG fake")
(job / "renders" / f"{{rid}}.json").write_text(json.dumps({{"status": "ok", "role": "exterior_front", "width": 640,
    "height": 360, "duration_seconds": 1.5, "engine_seen": request["engine"]}}))
"""


# EEVEE and Cycles test-render times (seconds) for different kinds of machine.
GPU, CPU_GL = "NVIDIA GeForce RTX 4070/PCIe/SSE2", "llvmpipe (LLVM 20.1.2, 256 bits)"
PROBES = {
    "pass": {"eevee": (0.4, GPU), "cycles": (3.0, "")},       # a desktop with a GPU
    "close": {"eevee": (4.0, GPU), "cycles": (3.0, "")},      # GPU, EEVEE a little slower: still preferred
    "slow": {"eevee": (12.0, GPU), "cycles": (3.0, "")},      # GPU, but EEVEE much slower: Cycles
    "software": {"eevee": (5.0, CPU_GL), "cycles": (4.2, "")},  # no GPU: decided by the renderer, not timing
    "fail": {"eevee": ("fail", ""), "cycles": (3.0, "")},
    "hang": {"eevee": ("hang", ""), "cycles": (3.0, "")},
}


def make_service(tmp_path: Path, probe: str = "pass", render: str = "pass", engine: str = "auto", timeout: float = 20) -> RenderService:
    script = tmp_path / "fake_blender"
    script.write_text(FAKE.format(
        python=sys.executable,
        probe=PROBES[probe],
        render={"pass": "", "fail": "print('boom'); sys.exit(1)", "hang": "time.sleep(30)"}[render],
    ))
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    jobs = tmp_path / "jobs"
    job = jobs / ("b" * 32)
    job.mkdir(parents=True)
    (job / "building.blend").write_bytes(b"blend")
    (job / "scene.json").write_text(json.dumps({"cameras": [{"name": "Camera_Exterior_Front", "tags": {"role": "exterior_front"}},
                                                            {"name": "Camera_FloorPlan_Ground", "tags": {"role": "floor_plan"}}]}))
    return RenderService(script, "binary", jobs, timeout, engine, probe_timeout=2)


@pytest.fixture(autouse=True)
def fresh_probe_cache():
    render_service._auto_engine.clear()
    yield
    render_service._auto_engine.clear()


def sent_engine(tmp_path: Path, result) -> str:
    request = json.loads((tmp_path / "jobs" / ("b" * 32) / "renders" / f"{result.render_id}.request.json").read_text())
    return request["engine"]


@pytest.mark.parametrize("probe", ["pass", "close"])
def test_auto_uses_eevee_where_it_is_practical(tmp_path: Path, probe: str) -> None:
    result = make_service(tmp_path, probe=probe).render("b" * 32, RenderRequest())
    assert result.engine == "eevee" and result.note is None and sent_engine(tmp_path, result) == "eevee"
    assert (result.width, result.height) == (640, 360)


@pytest.mark.parametrize("probe", ["fail", "hang"])
def test_auto_falls_back_when_eevee_is_unavailable(tmp_path: Path, probe: str) -> None:
    result = make_service(tmp_path, probe=probe).render("b" * 32, RenderRequest())
    assert result.engine == "cycles" and sent_engine(tmp_path, result) == "cycles"
    assert result.note and "not available" in result.note


def test_auto_prefers_cycles_when_eevee_is_much_slower(tmp_path: Path) -> None:
    result = make_service(tmp_path, probe="slow").render("b" * 32, RenderRequest())
    assert result.engine == "cycles"
    assert "renders faster than EEVEE on this machine (3.0 s against 12.0 s" in result.note


def test_auto_uses_cycles_on_a_software_renderer_whatever_the_timings(tmp_path: Path) -> None:
    result = make_service(tmp_path, probe="software").render("b" * 32, RenderRequest())
    assert result.engine == "cycles"
    assert "no GPU" in result.note and "llvmpipe" in result.note
    assert not (tmp_path / "jobs" / "_engine_probe" / "probe_cycles.json").exists()  # no need to time Cycles


@pytest.mark.parametrize(("name", "software"), [
    ("llvmpipe (LLVM 20.1.2, 256 bits)", True), ("SwiftShader Device", True), ("Microsoft Basic Render Driver", True),
    ("NVIDIA GeForce RTX 4070/PCIe/SSE2", False), ("Apple M2", False), ("AMD Radeon RX 7800 XT", False), ("", False),
])
def test_software_renderer_detection(name: str, software: bool) -> None:
    assert render_service.software_renderer(name) is software


def test_probes_run_once_per_executable(tmp_path: Path) -> None:
    service = make_service(tmp_path, probe="slow")
    service.render("b" * 32, RenderRequest())
    probes = tmp_path / "jobs" / "_engine_probe"
    for f in probes.glob("*.request.json"):
        f.unlink()  # a second probe would recreate these
    service.render("b" * 32, RenderRequest())
    assert not list(probes.glob("*.request.json"))


def test_explicit_engine_skips_the_probes(tmp_path: Path) -> None:
    result = make_service(tmp_path, probe="fail").render("b" * 32, RenderRequest(engine="eevee"))
    assert result.engine == "eevee" and not (tmp_path / "jobs" / "_engine_probe").exists()


def test_unknown_camera_is_rejected_before_blender_runs(tmp_path: Path) -> None:
    with pytest.raises(AppError) as caught:
        make_service(tmp_path).render("b" * 32, RenderRequest(camera="Camera_Secret"))
    assert caught.value.code == "unknown_camera" and "Camera_Exterior_Front" in caught.value.details["cameras"]
    assert not (tmp_path / "jobs" / ("b" * 32) / "renders").exists()


def test_render_failure(tmp_path: Path) -> None:
    with pytest.raises(AppError) as caught:
        make_service(tmp_path, render="fail", engine="cycles").render("b" * 32, RenderRequest())
    assert caught.value.code == "render_failed"


@pytest.mark.parametrize(("engine", "hint"), [("eevee", "OpenGL"), ("cycles", "Preview quality")])
def test_render_timeout_gives_an_engine_specific_hint(tmp_path: Path, engine: str, hint: str) -> None:
    with pytest.raises(AppError) as caught:
        make_service(tmp_path, render="hang", engine=engine, timeout=1).render("b" * 32, RenderRequest())
    assert caught.value.code == "render_timeout" and hint in caught.value.message


def test_job_without_a_model(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    (tmp_path / "jobs" / ("b" * 32) / "building.blend").unlink()
    with pytest.raises(AppError) as caught:
        service.render("b" * 32, RenderRequest())
    assert caught.value.code == "job_not_found"
