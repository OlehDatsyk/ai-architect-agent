"""Entry point Blender runs for each job.

    blender --background --factory-startup --python blender/scripts/runner.py -- <job_dir>
    python  blender/scripts/runner.py -- <job_dir>          (with the bpy module installed)

Reads <job_dir>/scene.json, builds it with the generators in this folder, saves
<job_dir>/building.blend and writes <job_dir>/result.json. Progress is appended to
<job_dir>/progress.jsonl as each stage starts. Exit code 0 on success, 1 on failure.
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402  (must come first: with the pip bpy module, bmesh only exists after bpy is imported)
import bmesh  # noqa: E402

from scene_builder import build_scene  # noqa: E402
from scene_validation import SceneError, validate_scene  # noqa: E402


def _job_dir() -> Path:
    if "--" not in sys.argv or sys.argv.index("--") + 1 >= len(sys.argv):
        raise SystemExit("usage: runner.py -- <job_dir>")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _world_bounds(obj) -> dict:
    corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return {
        "min": [round(min(c[i] for c in corners), 4) for i in range(3)],
        "max": [round(max(c[i] for c in corners), 4) for i in range(3)],
    }


def _mesh_check(obj) -> dict:
    """Closed (every edge shared by exactly two faces) and outward-facing (positive volume)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    manifold = all(edge.is_manifold for edge in bm.edges)
    volume = bm.calc_volume(signed=True)
    bm.free()
    return {"manifold": manifold, "volume": round(volume, 6)}


def _node_types(tree) -> set:
    types = set()
    for node in tree.nodes:
        types.add(node.bl_idname)
        if node.bl_idname == "ShaderNodeGroup" and node.node_tree:
            types |= _node_types(node.node_tree)
    return types


def _material_report(mat) -> dict:
    tree = mat.node_tree
    output = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)
    bsdf = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    transmission = next((i.default_value for i in bsdf.inputs if i.name == "Transmission Weight"), 0.0) if bsdf else 0.0
    return {
        "name": mat.name,
        "recipe": mat.get("aiarch_recipe"),
        "connected": bool(output and output.inputs["Surface"].is_linked),
        "node_types": sorted(_node_types(tree)),
        "transmission": round(float(transmission), 3),
    }


def main() -> int:
    job = _job_dir()
    started = time.perf_counter()
    stages: list[str] = []

    def report(stage: str) -> None:
        stages.append(stage)
        with (job / "progress.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"stage": stage, "t": round(time.perf_counter() - started, 3)}) + "\n")

    try:
        scene = validate_scene(json.loads((job / "scene.json").read_text(encoding="utf-8")))
        bpy.ops.wm.read_factory_settings(use_empty=True)
        objects = build_scene(scene, report)
        blend = job / "building.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        bpy.context.view_layer.update()
        _write(job / "result.json", {
            "status": "ok",
            "blender_version": bpy.app.version_string,
            "blend_file": blend.name,
            "stages": stages,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "materials": [_material_report(m) for m in bpy.data.materials],
            "cameras": [{"name": o.name, "type": o.data.type, "location": [round(v, 3) for v in o.location]}
                        for o in bpy.data.objects if o.type == "CAMERA"],
            "lights": [{"name": o.name, "type": o.data.type, "energy": o.data.energy,
                        "collection": o.users_collection[0].name} for o in bpy.data.objects if o.type == "LIGHT"],
            "worlds": [w.name for w in bpy.data.worlds],
            "view_layers": [v.name for v in bpy.context.scene.view_layers],
            "active_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
            "objects": [
                {"name": o.name, "collection": o.users_collection[0].name, "bounds": _world_bounds(o),
                 "material": o.active_material.name if o.active_material else None, **_mesh_check(o)}
                for o in objects
            ],
        })
        return 0
    except SceneError as exc:
        _write(job / "result.json", {"status": "error", "error": "invalid_scene", "message": str(exc), "stages": stages})
        return 1
    except Exception as exc:  # report every failure in result.json, never silently
        _write(job / "result.json", {"status": "error", "error": "build_failed", "message": str(exc),
                                     "traceback": traceback.format_exc(), "stages": stages})
        return 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # Exit with the job's status. os._exit is used because SystemExit raised inside Blender's
    # --python script does not reliably become Blender's exit code; all files are closed by now.
    os._exit(code)
