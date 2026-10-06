"""Walls. A wall with openings arrives as its solid pieces (between, above and below
openings); gable infills arrive as closed meshes."""

from mesh_utils import create_element


def create_wall(element: dict, collection, material):
    return create_element(element, collection, material, "wall")
