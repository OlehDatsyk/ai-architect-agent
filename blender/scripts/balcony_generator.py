"""Balcony slabs and glass balustrades."""

from mesh_utils import create_element


def create_balcony(element: dict, collection, material):
    return create_element(element, collection, material, "balcony")
