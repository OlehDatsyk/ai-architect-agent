"""Cameras, placed and aimed from the scene description (positions are computed by the backend)."""

import bpy
from mathutils import Vector


def aim(obj, location, target) -> None:
    """Point an object's -Z axis (cameras and lights look along it) at target, keeping +Y up."""
    obj.location = location
    direction = Vector(target) - Vector(location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def create_camera(spec: dict, collection):
    data = bpy.data.cameras.new(spec["name"])
    if spec["projection"] == "orthographic":
        data.type = "ORTHO"
        data.ortho_scale = spec["ortho_scale"]
    else:
        data.lens = spec["lens"]
    data.sensor_width = 36.0
    data.sensor_fit = "AUTO"
    data.clip_start = 0.05
    data.clip_end = spec["clip_end"]
    obj = bpy.data.objects.new(spec["name"], data)
    collection.objects.link(obj)
    aim(obj, spec["location"], spec["target"])
    for key, value in spec.get("tags", {}).items():
        obj[f"aiarch_{key}"] = value
    return obj
