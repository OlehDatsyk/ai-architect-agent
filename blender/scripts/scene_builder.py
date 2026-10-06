"""Builds a validated scene description into the current (empty) Blender file."""

import bpy
import mesh_utils
from balcony_generator import create_balcony
from camera_generator import create_camera
from door_generator import create_door
from environment_generator import create_site_area, create_vegetation
from floor_generator import create_room_floor, create_slab
from ground_generator import create_ground
from lighting_generator import create_light, create_view_layers, create_world
from material_generator import create_materials
from roof_generator import create_roof
from stair_generator import create_stair
from wall_generator import create_wall
from window_generator import create_window

GENERATORS = {
    "ground": create_ground,
    "slab": create_slab,
    "wall": create_wall,
    "room_floor": create_room_floor,
    "door": create_door,
    "window": create_window,
    "stair": create_stair,
    "balcony": create_balcony,
    "roof": create_roof,
    "site": create_site_area,
    "vegetation": create_vegetation,
}


def create_collections(specs: list[dict]) -> dict:
    created = {}
    scene_root = bpy.context.scene.collection
    for spec in specs:
        coll = bpy.data.collections.new(spec["name"])
        parent = created[spec["parent"]] if spec.get("parent") else scene_root
        parent.children.link(coll)
        created[spec["name"]] = coll
    return created


def build_scene(scene: dict, report) -> list:
    report("preparing_scene")
    collections = create_collections(scene["collections"])
    report("applying_materials")
    materials = create_materials(scene["materials"])
    mesh_utils.inner_materials.clear()
    mesh_utils.inner_materials.update(materials)
    report("generating_geometry")
    objects = []
    for element in scene["elements"]:
        generator = GENERATORS[element["kind"]]
        objects.append(generator(element, collections[element["collection"]], materials[element["material"]]))
    report("creating_lighting")
    worlds = {spec["name"]: create_world(spec) for spec in scene.get("worlds", [])}
    for spec in scene.get("lights", []):
        create_light(spec, collections[spec["collection"]])
    report("creating_cameras")
    cameras = {spec["name"]: create_camera(spec, collections["CAMERAS"]) for spec in scene.get("cameras", [])}

    render = scene.get("render", {})
    bscene = bpy.context.scene
    bscene.render.resolution_x = render.get("resolution_x", 1920)
    bscene.render.resolution_y = render.get("resolution_y", 1080)
    if render.get("active_camera") in cameras:
        bscene.camera = cameras[render["active_camera"]]
    if render.get("active_world") in worlds:
        bscene.world = worlds[render["active_world"]]
    for name in render.get("hidden_collections", []):
        collections[name].hide_render = True
    create_view_layers(scene.get("view_layers", []), collections)
    bscene.unit_settings.system = "METRIC"
    bscene.unit_settings.scale_length = 1.0
    return objects
