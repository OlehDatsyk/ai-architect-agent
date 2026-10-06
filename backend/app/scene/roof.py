"""Roofs as closed meshes, plus the wall infill that closes the ends of pitched roofs.

Local axes: u runs along the ridge, v across it, z up. The roof's underside meets the
top of the walls along their outer face, rising at the roof pitch towards the ridge.
The eaves extend `overhang` beyond the outer wall face.
"""

import math

from app.models.common import Axis
from app.models.roof import Roof, RoofType
from app.scene.model import Box3, MeshData
from app.scene.shapes import prism, to_world

THICKNESS = 0.2
FLAT_THICKNESS = 0.25


def roof_geometry(roof: Roof, ridge: Axis, width: float, depth: float, wall: float, z_top: float) -> tuple[list[Box3], MeshData | None, list[MeshData]]:
    """(boxes, mesh, wall infills). A flat roof is a box; pitched roofs are a mesh."""
    h, o = wall / 2, roof.overhang
    if roof.type is RoofType.FLAT:
        return [Box3(min=(-h - o, -h - o, z_top), max=(width + h + o, depth + h + o, z_top + FLAT_THICKNESS))], None, []

    lu, lv = (width, depth) if ridge is Axis.X else (depth, width)
    u0, u1, v0, v1 = -h - o, lu + h + o, -h - o, lv + h + o
    k = math.tan(math.radians(roof.pitch))
    z_e = z_top + THICKNESS - o * k  # eave top, chosen so the underside meets the wall's outer face at z_top
    t = THICKNESS

    if roof.type is RoofType.GABLE:
        vm = (v0 + v1) / 2
        zr = z_e + k * (vm - v0)
        top = [(u0, v0, z_e), (u0, vm, zr), (u0, v1, z_e), (u1, v0, z_e), (u1, vm, zr), (u1, v1, z_e)]
        local = top + [(u, v, z - t) for u, v, z in top]
        faces = [[0, 3, 4, 1], [1, 4, 5, 2], [6, 7, 10, 9], [7, 8, 11, 10],
                 [0, 6, 9, 3], [2, 5, 11, 8], [0, 1, 2, 8, 7, 6], [9, 10, 11, 5, 4, 3]]
        apex = z_top + k * (vm + h)
        gable = [(-h, z_top), (lv + h, z_top), (vm, apex)]
        infill = [prism(gable, -h, h, ridge), prism(gable, lu - h, lu + h, ridge)]
        return [], to_world(local, faces, ridge), infill

    if roof.type is RoofType.SHED:
        zh = z_e + k * (v1 - v0)
        top = [(u0, v0, z_e), (u1, v0, z_e), (u1, v1, zh), (u0, v1, zh)]
        local = top + [(u, v, z - t) for u, v, z in top]
        faces = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
        under = lambda v: z_top + k * (v + h)  # noqa: E731
        end = [(-h, z_top), (lv + h, z_top), (lv + h, under(lv + h))]
        high = [(lv - h, z_top), (lv + h, z_top), (lv + h, under(lv + h)), (lv - h, under(lv - h))]
        infill = [prism(end, -h, h, ridge), prism(end, lu - h, lu + h, ridge), prism(high, h, lu - h, ridge)]
        return [], to_world(local, faces, ridge), infill

    # Hip: the ridge runs along the longer side; the hips rise from each eave corner.
    span_u, span_v = u1 - u0, v1 - v0
    vm, zr = (v0 + v1) / 2, z_e + k * span_v / 2
    if span_u - span_v < 0.01:  # square plan: a pyramid
        top = [(u0, v0, z_e), (u1, v0, z_e), (u1, v1, z_e), (u0, v1, z_e), ((u0 + u1) / 2, vm, zr)]
        local = top + [(u, v, z - t) for u, v, z in top]
        faces = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [9, 6, 5], [9, 7, 6], [9, 8, 7], [9, 5, 8],
                 [0, 5, 6, 1], [1, 6, 7, 2], [2, 7, 8, 3], [3, 8, 5, 0]]
        return [], to_world(local, faces, ridge), []
    top = [(u0, v0, z_e), (u1, v0, z_e), (u1, v1, z_e), (u0, v1, z_e), (u0 + span_v / 2, vm, zr), (u1 - span_v / 2, vm, zr)]
    local = top + [(u, v, z - t) for u, v, z in top]
    faces = [[0, 1, 5, 4], [1, 2, 5], [4, 5, 2, 3], [3, 0, 4],
             [10, 11, 7, 6], [11, 8, 7], [9, 8, 11, 10], [10, 6, 9],
             [0, 6, 7, 1], [1, 7, 8, 2], [2, 8, 9, 3], [3, 9, 6, 0]]
    return [], to_world(local, faces, ridge), []
