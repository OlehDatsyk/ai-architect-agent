"""Run inside Blender: open a .blend and render a tiny Cycles image. Used by test_real_blender.py.

    <blender or python-with-bpy> render_smoke.py -- <file.blend> <out.png>
"""

import os
import sys

import bpy

blend, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.open_mainfile(filepath=blend)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 2
scene.render.resolution_x = scene.render.resolution_y = 48
camera = bpy.data.objects.new("SmokeCamera", bpy.data.cameras.new("SmokeCamera"))
scene.collection.objects.link(camera)
scene.camera = camera
camera.location = (-15.0, -20.0, 12.0)
camera.rotation_euler = (1.05, 0.0, -0.6)
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
sys.stdout.flush()
os._exit(0 if os.path.isfile(out) else 1)
