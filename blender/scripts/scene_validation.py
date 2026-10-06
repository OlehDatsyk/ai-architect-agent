"""Checks a scene.json before anything is built. Standard library only.

The runner builds only these element kinds, with these fields, from finite numbers within
sensible bounds, and with plain object names. Anything else stops the job: a scene file is
data, never instructions.
"""

import math
import re

RECIPES = {
    "brick", "white_render", "concrete", "timber_cladding", "dark_metal", "painted_plaster", "wood_flooring",
    "carpet", "tile", "slate", "clay_tile", "standing_seam_metal", "flat_roofing", "glass", "aluminium", "wood",
    "grass", "gravel", "paving", "foliage", "bark",
}
ALLOWED_KINDS = {"ground", "slab", "wall", "room_floor", "door", "window", "stair", "balcony", "roof", "site", "vegetation"}
MAX_BOXES = 400
MAX_VERTICES = 5000
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,59}$")
MAX_ELEMENTS = 20000
MAX_COORD = 1000.0


class SceneError(ValueError):
    pass


def _name(value: object, what: str) -> str:
    if not isinstance(value, str) or not NAME.match(value):
        raise SceneError(f"{what} has an invalid name: {value!r}")
    return value


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > MAX_COORD:
        raise SceneError(f"{what} is not a valid coordinate: {value!r}")
    return float(value)


def _check_mesh(mesh: object, name: str) -> None:
    if not isinstance(mesh, dict):
        raise SceneError(f"{name} has a malformed mesh.")
    vertices, faces = mesh.get("vertices"), mesh.get("faces")
    if not isinstance(vertices, list) or not 4 <= len(vertices) <= MAX_VERTICES:
        raise SceneError(f"{name} mesh needs 4 to {MAX_VERTICES} vertices.")
    for v in vertices:
        if not isinstance(v, list) or len(v) != 3:
            raise SceneError(f"{name} mesh has a malformed vertex.")
        for c in v:
            _number(c, f"{name} vertex")
    if not isinstance(faces, list) or not 4 <= len(faces) <= MAX_VERTICES:
        raise SceneError(f"{name} mesh needs at least 4 faces.")
    for f in faces:
        if (not isinstance(f, list) or len(f) < 3 or len(set(f)) != len(f)
                or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(vertices) for i in f)):
            raise SceneError(f"{name} mesh has an invalid face.")


def _vec(value: object, what: str) -> list:
    if not isinstance(value, list) or len(value) != 3:
        raise SceneError(f"{what} must be three numbers.")
    return [_number(v, what) for v in value]


def _colour(value: object, what: str) -> None:
    if not all(0 <= c <= 1 for c in _vec(value, what)):
        raise SceneError(f"{what} must be between 0 and 1.")


def _bounded(value: object, low: float, high: float, what: str) -> None:
    """A setting (not a coordinate): finite and within its own range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise SceneError(f"{what} must be between {low} and {high} (got {value!r}).")


def _check_extras(scene: dict, collection_names: set) -> None:
    names = set()
    for cam in scene.get("cameras", []):
        names.add(_name(cam.get("name"), "Camera"))
        if cam.get("projection") not in ("perspective", "orthographic"):
            raise SceneError(f"Camera {cam['name']} has an unknown projection.")
        if _vec(cam.get("location"), "Camera location") == _vec(cam.get("target"), "Camera target"):
            raise SceneError(f"Camera {cam['name']} looks at its own position.")
        _bounded(cam.get("lens"), 8, 300, "Camera lens")
        _bounded(cam.get("ortho_scale"), 0.01, 1000, "Camera scale")
        _bounded(cam.get("clip_end"), 1, 10000, "Camera clip end")
    if scene.get("cameras") and "CAMERAS" not in collection_names:
        raise SceneError("Cameras need a CAMERAS collection.")
    for light in scene.get("lights", []):
        names.add(_name(light.get("name"), "Light"))
        if light.get("kind") not in ("sun", "area"):
            raise SceneError(f"Light {light['name']} has an unknown kind.")
        if light.get("collection") not in collection_names:
            raise SceneError(f"Light {light['name']} refers to an unknown collection.")
        if _vec(light.get("location"), "Light location") == _vec(light.get("target"), "Light target"):
            raise SceneError(f"Light {light['name']} points at its own position.")
        _colour(light.get("colour"), "Light colour")
        _bounded(light.get("energy"), 0, 100000, "Light energy")
        _bounded(light.get("size"), 0.001, 20, "Light size")
    worlds = set()
    for world in scene.get("worlds", []):
        worlds.add(_name(world.get("name"), "World"))
        for key in ("horizon", "zenith", "ground"):
            _colour(world.get(key), f"World {key}")
        _bounded(world.get("strength"), 0, 10, "World strength")
    for layer in scene.get("view_layers", []):
        _name(layer.get("name"), "View layer")
        if not isinstance(layer.get("exclude"), list) or not set(layer["exclude"]) <= collection_names:
            raise SceneError(f"View layer {layer.get('name')} excludes an unknown collection.")
    render = scene.get("render", {})
    _bounded(render.get("resolution_x", 1920), 16, 8192, "Resolution")
    _bounded(render.get("resolution_y", 1080), 16, 8192, "Resolution")
    if render.get("active_camera") not in (None, *[c["name"] for c in scene.get("cameras", [])]):
        raise SceneError("The active camera is not defined.")
    if render.get("active_world") not in (None, *worlds):
        raise SceneError("The active world is not defined.")
    if not set(render.get("hidden_collections", [])) <= collection_names:
        raise SceneError("A hidden collection is not defined.")
    if len(names) != len(scene.get("cameras", [])) + len(scene.get("lights", [])):
        raise SceneError("Camera and light names must be unique.")


def validate_scene(scene: object) -> dict:
    if not isinstance(scene, dict) or scene.get("schema_version") != "1.0":
        raise SceneError("Unsupported scene file (expected schema_version 1.0).")
    collections = scene.get("collections")
    materials = scene.get("materials")
    elements = scene.get("elements")
    if not isinstance(collections, list) or not isinstance(materials, list) or not isinstance(elements, list):
        raise SceneError("Scene needs collections, materials and elements lists.")
    if len(elements) > MAX_ELEMENTS:
        raise SceneError(f"Scene has {len(elements)} elements; the limit is {MAX_ELEMENTS}.")

    collection_names = set()
    for c in collections:
        collection_names.add(_name(c.get("name"), "Collection"))
        if c.get("parent") is not None and c["parent"] not in collection_names:
            raise SceneError(f"Collection {c['name']} names parent {c['parent']!r} before it is defined.")

    material_names = set()
    for m in materials:
        material_names.add(_name(m.get("name"), "Material"))
        colour = m.get("base_color")
        if not isinstance(colour, list) or len(colour) != 3 or not all(0 <= _number(v, "Colour") <= 1 for v in colour):
            raise SceneError(f"Material {m['name']} has an invalid colour.")
        if m.get("recipe") not in RECIPES:
            raise SceneError(f"Material {m['name']} uses unknown recipe {m.get('recipe')!r}.")

    seen = set()
    for e in elements:
        if e.get("kind") not in ALLOWED_KINDS:
            raise SceneError(f"Unknown element kind {e.get('kind')!r}.")
        name = _name(e.get("name"), "Element")
        if name in seen:
            raise SceneError(f"Duplicate object name {name}.")
        seen.add(name)
        if e.get("collection") not in collection_names:
            raise SceneError(f"{name} refers to unknown collection {e.get('collection')!r}.")
        if e.get("material") not in material_names:
            raise SceneError(f"{name} refers to unknown material {e.get('material')!r}.")
        if (e.get("inner_material") is None) != (e.get("inward") is None):
            raise SceneError(f"{name} needs both an inner material and an inward direction, or neither.")
        if e.get("inner_material") is not None and (e["inner_material"] not in material_names or e["inward"] not in ("+x", "-x", "+y", "-y")):
            raise SceneError(f"{name} has an invalid inner material or direction.")
        boxes, mesh = e.get("boxes") or [], e.get("mesh")
        if bool(boxes) == (mesh is not None):
            raise SceneError(f"{name} needs either boxes or a mesh.")
        if not isinstance(boxes, list) or len(boxes) > MAX_BOXES:
            raise SceneError(f"{name} has too many boxes.")
        for box in boxes:
            lo = [_number(v, f"{name} min") for v in box.get("min", [])]
            hi = [_number(v, f"{name} max") for v in box.get("max", [])]
            if len(lo) != 3 or len(hi) != 3 or any(b <= a for a, b in zip(lo, hi)):
                raise SceneError(f"{name} has an empty or malformed box.")
        if mesh is not None:
            _check_mesh(mesh, name)
        tags = e.get("tags", {})
        if not isinstance(tags, dict) or not all(isinstance(k, str) and isinstance(v, str) and len(v) < 200 for k, v in tags.items()):
            raise SceneError(f"{name} has invalid tags.")
    _check_extras(scene, collection_names)
    return scene
