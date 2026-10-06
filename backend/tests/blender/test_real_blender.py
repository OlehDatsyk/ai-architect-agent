"""Builds scenes in real Blender and checks every object against the scene description.

Runs when BLENDER_EXECUTABLE is set (a Blender binary, or a Python interpreter with the bpy
module installed: pip install bpy). Skipped otherwise.

    BLENDER_EXECUTABLE=/path/to/blender python -m pytest tests/blender -v
"""

import os
import subprocess
from pathlib import Path

import pytest

from app.scene.compiler import compile_scene
from app.services.blender_service import BlenderService
from tests.scene_cases import example_specs

EXECUTABLE = os.environ.get("BLENDER_EXECUTABLE")
pytestmark = [
    pytest.mark.blender,
    pytest.mark.skipif(not EXECUTABLE, reason="Set BLENDER_EXECUTABLE to run real Blender tests."),
]


@pytest.mark.parametrize("case", sorted(example_specs()))
def test_blender_builds_exactly_what_the_scene_describes(case: str, tmp_path: Path) -> None:
    scene = compile_scene(example_specs()[case])
    result = BlenderService(Path(EXECUTABLE), "auto", tmp_path / "jobs", 300).build(scene)

    built = {o["name"]: o for o in result.objects}
    assert set(built) == {e.name for e in scene.elements}, "Blender renamed or dropped objects"
    for element in scene.elements:
        obj = built[element.name]
        assert obj["collection"] == element.collection
        assert obj["material"] == element.material
        for i in range(3):
            assert obj["bounds"]["min"][i] == pytest.approx(element.bounds.min[i], abs=1e-4), element.name
            assert obj["bounds"]["max"][i] == pytest.approx(element.bounds.max[i], abs=1e-4), element.name
        assert obj["manifold"], f"{element.name} is not a closed mesh"
        assert obj["volume"] > 0, f"{element.name} has inward-facing normals"
    assert result.blend_path.stat().st_size > 10_000
    header = result.blend_path.read_bytes()[:7]
    # Uncompressed .blend files start with "BLENDER"; Blender 5 compresses with Zstandard by default.
    assert header == b"BLENDER" or header[:4] == b"\x28\xb5\x2f\xfd"


PROCEDURAL_ONLY_FORBIDDEN = {"ShaderNodeTexImage", "ShaderNodeTexEnvironment", "ShaderNodeScript"}


@pytest.mark.parametrize("case", ["example:british-family-house", "example:scandinavian-house", "example:luxury-house"])
def test_every_material_is_procedural_and_connected(case: str, tmp_path: Path) -> None:
    scene = compile_scene(example_specs()[case])
    result = BlenderService(Path(EXECUTABLE), "auto", tmp_path / "jobs", 300).build(scene)
    import json

    report = json.loads((result.blend_path.parent / "result.json").read_text())
    built = {m["name"]: m for m in report["materials"]}
    assert set(built) == {m.name for m in scene.materials}
    for material in scene.materials:
        info = built[material.name]
        assert info["recipe"] == material.recipe.value
        assert info["connected"], f"{material.name} is not wired to the material output"
        assert not set(info["node_types"]) & PROCEDURAL_ONLY_FORBIDDEN, f"{material.name} uses image or script nodes"
        assert "ShaderNodeGroup" in info["node_types"], f"{material.name} does not use the shared texture coordinates"
        assert info["transmission"] == (1.0 if material.recipe.value == "glass" else 0.0)
    assert "applying_materials" in result.stages


def _blender_command(script: Path, *args: str) -> list[str]:
    exe = Path(EXECUTABLE)
    if exe.name.lower().startswith("python"):
        return [str(exe), str(script), "--", *args]
    return [str(exe), "--background", "--factory-startup", "--python", str(script), "--", *args]


@pytest.mark.parametrize("case", ["example:british-family-house", "example:modern-bungalow", "example:small-office", "planned:luxury-house"])
def test_blender_cameras_see_what_they_should(case: str, tmp_path: Path) -> None:
    """Uses Blender's own world_to_camera_view, so a mismatch between the backend's camera maths
    and Blender's camera conventions would fail here."""
    import json

    scene = compile_scene(example_specs()[case])
    result = BlenderService(Path(EXECUTABLE), "auto", tmp_path / "jobs", 300).build(scene)
    completed = subprocess.run(_blender_command(Path(__file__).with_name("camera_check.py"), str(result.blend_path)),
                               capture_output=True, text=True, timeout=300)
    line = next(out for out in completed.stdout.splitlines() if out.startswith("CAMERA_CHECK "))
    report = json.loads(line[len("CAMERA_CHECK "):])
    assert report["exterior"] and all(report["exterior"].values()), report["exterior"]
    assert all(report["interior"].values()), report["interior"]
    assert report["plans"] and all(report["plans"].values()), report["plans"]
    assert report["worlds"] == ["World_Day", "World_Evening"]  # both survive saving
    assert report["active_world"] == "World_Day" and report["hidden_collections"] == ["LIGHTS_EVENING"]
    for layer in scene.view_layers:
        assert report["view_layers"][layer.name] == sorted(layer.exclude)
    assert {"creating_lighting", "creating_cameras"} <= set(result.stages)


def test_built_house_renders(tmp_path: Path) -> None:
    scene = compile_scene(example_specs()["example:british-family-house"])
    result = BlenderService(Path(EXECUTABLE), "auto", tmp_path / "jobs", 300).build(scene)
    image = tmp_path / "smoke.png"
    completed = subprocess.run(_blender_command(Path(__file__).with_name("render_smoke.py"), str(result.blend_path), str(image)),
                               capture_output=True, text=True, timeout=300)
    assert completed.returncode == 0, completed.stdout[-2000:]
    assert image.stat().st_size > 500


def test_blender_rejects_a_tampered_scene(tmp_path: Path) -> None:
    scene = compile_scene(next(iter(example_specs().values())))
    tampered = scene.model_copy(deep=True)
    object.__setattr__(tampered.elements[0], "kind", "python")  # bypass model validation, as an attacker would
    from app.core.errors import AppError

    with pytest.raises(AppError) as caught:
        BlenderService(Path(EXECUTABLE), "auto", tmp_path / "jobs", 300).build(tampered)
    assert "Unknown element kind" in caught.value.message


def test_renders_from_a_built_house(tmp_path: Path) -> None:
    """Day and evening exterior with the default engine, then a floor plan with Cycles."""
    from app.services import render_service
    from app.services.render_service import RenderRequest, RenderService

    render_service._auto_engine.clear()
    scene = compile_scene(example_specs()["example:british-family-house"])
    built = BlenderService(Path(EXECUTABLE), "auto", tmp_path / "jobs", 300).build(scene)
    renders = RenderService(Path(EXECUTABLE), "auto", tmp_path / "jobs", 600, "auto", probe_timeout=90)

    day = renders.render(built.job_id, RenderRequest(camera="Camera_Exterior_Front", preset="day"))
    assert (day.width, day.height) == (640, 360)  # 1280x720 at preview quality's 50%
    assert day.contrast > 0.05, "the day render is nearly uniform"
    assert day.engine in ("eevee", "cycles") and (day.engine == "eevee") == (day.note is None)
    print(f"\nauto engine on this machine: {day.engine} ({day.note or 'EEVEE practical'})")

    evening = renders.render(built.job_id, RenderRequest(camera="Camera_Exterior_Front", preset="evening", engine=day.engine))
    assert evening.brightness < day.brightness * 0.6, (day.brightness, evening.brightness)

    plan = renders.render(built.job_id, RenderRequest(camera="Camera_FloorPlan_Ground", engine="cycles"))
    assert plan.view_layer == "FloorPlan_Ground" and plan.role == "floor_plan" and plan.contrast > 0.05
