"""Sun and area lights, gradient sky worlds, and the day / evening presets."""

import math

import bpy
from camera_generator import aim


def create_light(spec: dict, collection):
    if spec["kind"] == "sun":
        data = bpy.data.lights.new(spec["name"], "SUN")
        data.angle = math.radians(spec["size"])
    else:
        data = bpy.data.lights.new(spec["name"], "AREA")
        data.shape = "SQUARE"
        data.size = spec["size"]
    data.energy = spec["energy"]
    data.color = spec["colour"]
    obj = bpy.data.objects.new(spec["name"], data)
    collection.objects.link(obj)
    aim(obj, spec["location"], spec["target"])
    for key, value in spec.get("tags", {}).items():
        obj[f"aiarch_{key}"] = value
    return obj


def create_world(spec: dict):
    """A sky that blends from the horizon colour to the zenith colour, with a ground colour below.
    Built from basic nodes so it behaves the same in every Blender version (the Sky Texture
    node's models changed between Blender 4 and 5)."""
    world = bpy.data.worlds.new(spec["name"])
    # Blender drops data-blocks nobody uses when it saves; only one world is assigned to the
    # scene, so keep the others (the evening preset) explicitly.
    world.use_fake_user = True
    if world.node_tree is None:
        world.use_nodes = True
    tree = world.node_tree
    tree.nodes.clear()
    coords = tree.nodes.new("ShaderNodeTexCoord")
    split = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(coords.outputs["Normal"], split.inputs[0])  # view direction for the world background
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.5           # straight down maps to 0, horizon to 0.5
    ramp.color_ramp.elements[0].color = tuple(spec["ground"]) + (1.0,)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = tuple(spec["zenith"]) + (1.0,)
    horizon = ramp.color_ramp.elements.new(0.52)
    horizon.color = tuple(spec["horizon"]) + (1.0,)
    remap = tree.nodes.new("ShaderNodeMapRange")           # z from [-1, 1] to [0, 1]
    remap.inputs["From Min"].default_value = -1.0
    remap.inputs["From Max"].default_value = 1.0
    tree.links.new(split.outputs["Z"], remap.inputs["Value"])
    tree.links.new(remap.outputs["Result"], ramp.inputs["Fac"])
    background = tree.nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = spec["strength"]
    tree.links.new(ramp.outputs["Color"], background.inputs["Color"])
    output = tree.nodes.new("ShaderNodeOutputWorld")
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    return world


def _exclude(layer_collection, names: set) -> None:
    for child in layer_collection.children:
        if child.name in names:
            child.exclude = True
        else:
            _exclude(child, names)


def create_view_layers(specs: list[dict], collections: dict) -> None:
    """Extra view layers that leave out collections, e.g. the roof and upper floors for a plan."""
    scene = bpy.context.scene
    for spec in specs:
        layer = scene.view_layers.new(spec["name"])
        _exclude(layer.layer_collection, set(spec["exclude"]))
