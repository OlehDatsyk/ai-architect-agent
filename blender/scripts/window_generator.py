"""Window frames and glass. Each window is two objects: Window_<Room>_NN (frame) and _Glass."""

from mesh_utils import create_element


def create_window(element: dict, collection, material):
    return create_element(element, collection, material, "window")
