"""Door frames and leaves. Each door is two objects: Door_<A>_<B>_NN (frame) and _Leaf."""

from mesh_utils import create_element


def create_door(element: dict, collection, material):
    return create_element(element, collection, material, "door")
