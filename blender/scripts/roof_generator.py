"""Roofs: a slab for flat roofs, a closed mesh for gable, hip and shed roofs."""

from mesh_utils import create_element


def create_roof(element: dict, collection, material):
    return create_element(element, collection, material, "roof")
