"""Structural slabs (with stairwell openings) and the floor finish of each room."""

from mesh_utils import create_element


def create_slab(element: dict, collection, material):
    return create_element(element, collection, material, "slab")


def create_room_floor(element: dict, collection, material):
    return create_element(element, collection, material, "room_floor")
