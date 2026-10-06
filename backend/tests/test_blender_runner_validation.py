"""The Blender runner's own input checks (standard library only, so testable without Blender)."""

import copy
import json
import math
import sys
from pathlib import Path

import pytest

from app.models import BuildingSpecification
from app.scene.compiler import compile_scene
from tests.helpers import example

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "blender" / "scripts"))
from scene_validation import SceneError, validate_scene

SCENE = json.loads(compile_scene(BuildingSpecification.model_validate(example())).model_dump_json())


def _roof(scene: dict) -> dict:
    return next(e for e in scene["elements"] if e["kind"] == "roof")


def broken(change) -> dict:
    scene = copy.deepcopy(SCENE)
    change(scene)
    return scene


def test_compiled_scene_is_accepted() -> None:
    assert validate_scene(copy.deepcopy(SCENE))["schema_version"] == "1.0"


@pytest.mark.parametrize(("label", "change"), [
    ("unknown kind", lambda s: s["elements"][0].update(kind="python")),
    ("code in a name", lambda s: s["elements"][0].update(name="x; import os")),
    ("path in a name", lambda s: s["elements"][0].update(name="../../etc")),
    ("infinite coordinate", lambda s: s["elements"][0]["boxes"][0].update(min=[math.inf, 0, 0])),
    ("huge coordinate", lambda s: s["elements"][0]["boxes"][0].update(max=[1e9, 1, 1])),
    ("empty box", lambda s: s["elements"][0]["boxes"][0].update(max=s["elements"][0]["boxes"][0]["min"])),
    ("boolean coordinate", lambda s: s["elements"][0]["boxes"][0].update(min=[True, 0, 0])),
    ("boxes and a mesh", lambda s: s["elements"][0].update(mesh={"vertices": [[0, 0, 0]] * 4, "faces": [[0, 1, 2]] * 4})),
    ("no geometry", lambda s: s["elements"][0].update(boxes=[])),
    ("too many boxes", lambda s: s["elements"][0].update(boxes=s["elements"][0]["boxes"] * 401)),
    ("face index out of range", lambda s: _roof(s)["mesh"]["faces"].append([0, 1, 9999])),
    ("repeated face index", lambda s: _roof(s)["mesh"]["faces"].append([0, 0, 1])),
    ("non-integer face index", lambda s: _roof(s)["mesh"]["faces"].append([0, 1, 2.5])),
    ("infinite vertex", lambda s: _roof(s)["mesh"]["vertices"].append([math.nan, 0, 0])),
    ("duplicate name", lambda s: s["elements"][1].update(name=s["elements"][0]["name"])),
    ("unknown collection", lambda s: s["elements"][0].update(collection="Nowhere")),
    ("unknown material", lambda s: s["elements"][0].update(material="MAT_Nope")),
    ("bad colour", lambda s: s["materials"][0].update(base_color=[2, 0, 0])),
    ("unknown recipe", lambda s: s["materials"][0].update(recipe="import_image")),
    ("unknown plant kind", lambda s: next(e for e in s["elements"] if e["kind"] == "vegetation").update(kind="python_tree")),
    ("missing recipe", lambda s: s["materials"][0].pop("recipe")),
    ("camera looking at itself", lambda s: s["cameras"][0].update(target=s["cameras"][0]["location"])),
    ("unknown projection", lambda s: s["cameras"][0].update(projection="fisheye")),
    ("lens out of range", lambda s: s["cameras"][0].update(lens=2)),
    ("light in unknown collection", lambda s: s["lights"][0].update(collection="Nowhere")),
    ("unknown light kind", lambda s: s["lights"][0].update(kind="spot")),
    ("boolean energy", lambda s: s["lights"][0].update(energy=True)),
    ("huge energy", lambda s: s["lights"][0].update(energy=1e9)),
    ("light colour out of range", lambda s: s["lights"][0].update(colour=[1, 2, 0])),
    ("world strength out of range", lambda s: s["worlds"][0].update(strength=50)),
    ("view layer excludes unknown collection", lambda s: s["view_layers"][0]["exclude"].append("Ghost")),
    ("unknown active camera", lambda s: s["render"].update(active_camera="Camera_Nope")),
    ("resolution out of range", lambda s: s["render"].update(resolution_x=100000)),
    ("hidden collection unknown", lambda s: s["render"]["hidden_collections"].append("Ghost")),
    ("duplicate camera name", lambda s: s["cameras"][1].update(name=s["cameras"][0]["name"])),
    ("inner material without direction", lambda s: next(e for e in s["elements"] if e.get("inner_material")).pop("inward")),
    ("bad inward direction", lambda s: next(e for e in s["elements"] if e.get("inner_material")).update(inward="+z")),
    ("parent defined later", lambda s: s["collections"].insert(0, {"name": "Early", "parent": "Later"})),
    ("wrong version", lambda s: s.update(schema_version="9")),
    ("non-string tag", lambda s: s["elements"][0].update(tags={"x": 1})),
])
def test_invalid_scenes_are_rejected(label: str, change) -> None:
    with pytest.raises(SceneError):
        validate_scene(broken(change))
