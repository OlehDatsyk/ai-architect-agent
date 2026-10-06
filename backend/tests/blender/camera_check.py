"""Run inside Blender: verify cameras with Blender's own projection. Prints one JSON line.

    <blender or python-with-bpy> camera_check.py -- <file.blend>
"""

import json
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=blend)
scene = bpy.context.scene
report: dict = {"exterior": {}, "interior": {}, "plans": {}}

building = [o for o in bpy.data.objects if o.type == "MESH" and o.get("aiarch_kind") not in ("ground", "site", "vegetation")]
corners = [o.matrix_world @ Vector(c) for o in building for c in o.bound_box]
lo = Vector([min(p[i] for p in corners) for i in range(3)])
hi = Vector([max(p[i] for p in corners) for i in range(3)])
box = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]


def in_frame(cam, points, margin=0.0) -> bool:
    for p in points:
        v = world_to_camera_view(scene, cam, p)
        if v.z <= 0 or not (margin <= v.x <= 1 - margin and margin <= v.y <= 1 - margin):
            return False
    return True


def excluded(layer_collection) -> list:
    found = []
    for child in layer_collection.children:
        found += [child.name] if child.exclude else excluded(child)
    return found


for cam in (o for o in bpy.data.objects if o.type == "CAMERA"):
    role = cam.get("aiarch_role", "")
    if role.startswith("exterior"):
        report["exterior"][cam.name] = in_frame(cam, box, 0.02)
    elif role.startswith("interior"):
        room = next(o for o in bpy.data.objects if o.get("aiarch_room_id") == cam["aiarch_room_id"] and o.get("aiarch_kind") == "room_floor")
        rc = [room.matrix_world @ Vector(c) for c in room.bound_box]
        lo_r = [min(p[i] for p in rc) for i in range(3)]
        hi_r = [max(p[i] for p in rc) for i in range(3)]
        inside = all(lo_r[i] < cam.location[i] < hi_r[i] for i in (0, 1))
        floor_z = hi_r[2]
        standing = floor_z + 1.0 < cam.location.z < floor_z + 2.4  # eye height, below the ceiling
        # The room's centre, a metre above its floor, must be in view: the camera looks into the room.
        centre = Vector(((lo_r[0] + hi_r[0]) / 2, (lo_r[1] + hi_r[1]) / 2, floor_z + 1.0))
        report["interior"][cam.name] = inside and standing and in_frame(cam, [centre], 0.1)
    elif role == "floor_plan":
        level = cam["aiarch_floor"]
        walls = [o.matrix_world @ Vector(c) for o in bpy.data.objects
                 if o.get("aiarch_kind") == "wall" and o.get("aiarch_floor") == level for c in o.bound_box]
        layer = scene.view_layers.get(cam.get("aiarch_view_layer", ""))
        hides_roof = layer is not None and "ROOF" in excluded(layer.layer_collection)
        report["plans"][cam.name] = in_frame(cam, walls, 0.0) and hides_roof

report["view_layers"] = {layer.name: sorted(excluded(layer.layer_collection)) for layer in scene.view_layers}
report["worlds"] = sorted(w.name for w in bpy.data.worlds)  # as saved in the file, not as created
report["active_world"] = scene.world.name if scene.world else None
report["hidden_collections"] = sorted(c.name for c in bpy.data.collections if c.hide_render)
print("CAMERA_CHECK " + json.dumps(report))
sys.stdout.flush()
os._exit(0)
