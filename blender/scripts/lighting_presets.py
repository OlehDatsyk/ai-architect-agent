"""Switch a built scene between its lighting presets. Used by the render runner, and usable
from Blender's Python console:  import lighting_presets; lighting_presets.apply_preset(bpy.context.scene, "evening")"""

PRESET_COLLECTIONS = {"day": "LIGHTS_DAY", "evening": "LIGHTS_EVENING"}
PRESET_WORLDS = {"day": "World_Day", "evening": "World_Evening"}


def _find(layer_collection, name: str):
    if layer_collection.name == name:
        return layer_collection
    for child in layer_collection.children:
        found = _find(child, name)
        if found is not None:
            return found
    return None


def apply_preset(scene, preset: str) -> None:
    import bpy

    if preset not in PRESET_WORLDS:
        raise ValueError(f"unknown lighting preset {preset!r}")
    scene.world = bpy.data.worlds[PRESET_WORLDS[preset]]
    for layer in scene.view_layers:  # every view layer, including the floor-plan layers
        for name, collection in PRESET_COLLECTIONS.items():
            found = _find(layer.layer_collection, collection)
            if found is not None:
                found.exclude = name != preset
