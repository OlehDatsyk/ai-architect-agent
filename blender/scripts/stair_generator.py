"""Stairs: one solid step per tread, rising from the floor finish."""

from mesh_utils import create_element


def create_stair(element: dict, collection, material):
    return create_element(element, collection, material, "stair")
