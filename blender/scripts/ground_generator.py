"""The ground the building stands on."""

from mesh_utils import create_element


def create_ground(element: dict, collection, material):
    return create_element(element, collection, material, "ground")
