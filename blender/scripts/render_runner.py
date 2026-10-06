"""Renders one image from a built scene.

    blender --background --factory-startup --python blender/scripts/render_runner.py -- <job_dir> <request.json>
    python  blender/scripts/render_runner.py -- <job_dir> <request.json>       (with the bpy module)

Opens <job_dir>/building.blend, applies the lighting preset, picks the camera (and, for floor
plans, the camera's own view layer), renders to <job_dir>/renders/<render_id>.png and writes
<render_id>.json next to it. With the request {"probe": "eevee"} it instead renders a tiny
empty scene with EEVEE, to find out whether EEVEE works on this machine.
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
from lighting_presets import apply_preset
from render_settings import QUALITY, RENDER_ID, RESOLUTIONS, RenderRequestError, validate_render_request


def eevee_engine() -> str:
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"  # 4.2-4.x / 5.x


def probe(engine: str, job: Path) -> int:
    """Render a small scene with the materials that make engines slow (see-through glass, brick)
    and record how long it took, so the backend can pick the practical engine for this machine."""
    from material_generator import create_material
    from mesh_utils import create_element

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    world = bpy.data.worlds.new("ProbeWorld")
    scene.world = world
    collection = scene.collection
    brick = create_material({"name": "ProbeBrick", "recipe": "brick", "base_color": (0.42, 0.14, 0.08)})
    glass = create_material({"name": "ProbeGlass", "recipe": "glass", "base_color": (0.6, 0.72, 0.78)})
    create_element({"name": "ProbeWall", "boxes": [{"min": [0, 0, 0], "max": [4, 0.3, 2.5]}]}, collection, brick, "probe")
    create_element({"name": "ProbeGlass", "boxes": [{"min": [1, -0.3, 0.8], "max": [3, -0.28, 2.0]}]}, collection, glass, "probe")
    sun = bpy.data.objects.new("ProbeSun", bpy.data.lights.new("ProbeSun", "SUN"))
    collection.objects.link(sun)
    sun.rotation_euler = (0.9, 0.0, 0.5)
    camera = bpy.data.objects.new("ProbeCamera", bpy.data.cameras.new("ProbeCamera"))
    collection.objects.link(camera)
    camera.location = (2.0, -6.0, 1.6)
    camera.rotation_euler = (1.5, 0.0, 0.0)
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 16
    else:
        scene.render.engine = eevee_engine()
        scene.eevee.taa_render_samples = 16
    out = job / f"probe_{engine}.png"
    scene.render.filepath = str(out)
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    seconds = time.perf_counter() - started
    renderer = vendor = ""
    if engine == "eevee":
        try:  # which OpenGL implementation drew it: a real GPU, or a software rasteriser such as llvmpipe
            import gpu

            renderer, vendor = gpu.platform.renderer_get(), gpu.platform.vendor_get()
        except Exception:  # an unknown renderer is treated like a real GPU; the timing check still applies
            pass
    (job / f"probe_{engine}.json").write_text(json.dumps({"engine": engine, "ok": out.is_file(), "seconds": round(seconds, 3),
                                                         "gpu_renderer": renderer, "gpu_vendor": vendor}))
    return 0 if out.is_file() else 1


def image_stats(path: Path) -> tuple[float, float]:
    """Mean and standard deviation of brightness (0-1), sampled across the image.
    A blank or uniform render has a tiny standard deviation."""
    image = bpy.data.images.load(str(path))
    pixels = image.pixels[:]
    values = [(pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3 for i in range(0, len(pixels), 4 * 17)]
    bpy.data.images.remove(image)
    mean = sum(values) / len(values)
    return mean, (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def render(job: Path, request: dict) -> dict:
    bpy.ops.wm.open_mainfile(filepath=str(job / "building.blend"))
    scene = bpy.context.scene
    cameras = {o.name for o in bpy.data.objects if o.type == "CAMERA"}
    request = validate_render_request(request, cameras)

    apply_preset(scene, request["preset"])
    camera = bpy.data.objects[request["camera"]]
    scene.camera = camera
    if camera.get("aiarch_role") == "floor_plan":
        layer_name = camera.get("aiarch_view_layer")
        if layer_name not in scene.view_layers:
            # Never fall back to the full scene: the plan would silently show the roof.
            raise RuntimeError(f"{camera.name} has no floor-plan view layer; rebuild the design to add it.")
    else:
        layer_name = "ViewLayer"
    # Exactly one view layer: it is the one we want, and EEVEE stalls headless when several render at once.
    for layer in scene.view_layers:
        layer.use = layer.name == layer_name

    cycles_samples, eevee_samples, percentage = QUALITY[request["quality"]]
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTIONS[request["resolution"]]
    scene.render.resolution_percentage = percentage
    if request["engine"] == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = cycles_samples
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.use_denoising = True
    else:
        scene.render.engine = eevee_engine()
        scene.eevee.taa_render_samples = eevee_samples
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    out = job / "renders" / f"{request['render_id']}.png"
    out.parent.mkdir(exist_ok=True)
    scene.render.filepath = str(out)
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    if not out.is_file():
        raise RuntimeError("Blender finished rendering but no image was written.")
    brightness, contrast = image_stats(out)
    if contrast < 0.005:
        raise RuntimeError("The render came out blank (a single flat colour).")
    return {
        "status": "ok", "render_id": request["render_id"], "image": out.name, "camera": camera.name,
        "role": camera.get("aiarch_role"), "view_layer": layer_name, "preset": request["preset"],
        "quality": request["quality"], "engine": request["engine"], "blender_version": bpy.app.version_string,
        "width": scene.render.resolution_x * percentage // 100, "height": scene.render.resolution_y * percentage // 100,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "brightness": round(brightness, 4), "contrast": round(contrast, 4),
    }


def main() -> int:
    args = sys.argv[sys.argv.index("--") + 1:]
    job, request = Path(args[0]).resolve(), json.loads(Path(args[1]).read_text(encoding="utf-8"))
    if isinstance(request, dict) and set(request) == {"probe"} and request["probe"] in ("eevee", "cycles"):
        return probe(request["probe"], job)
    # The render ID becomes a file name, so it must be checked before it is used for anything.
    render_id = request.get("render_id") if isinstance(request, dict) else None
    safe_id = render_id if isinstance(render_id, str) and RENDER_ID.match(render_id) else None
    try:
        result = render(job, request)
        code = 0
    except RenderRequestError as exc:
        result, code = {"status": "error", "error": "invalid_request", "message": str(exc)}, 1
    except Exception as exc:  # every failure is reported, never silently
        result, code = {"status": "error", "error": "render_failed", "message": str(exc), "traceback": traceback.format_exc()}, 1
    if safe_id is not None:
        (job / "renders").mkdir(exist_ok=True)
        (job / "renders" / f"{safe_id}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        print(json.dumps(result))  # no safe file name: report on stdout only
    return code


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
