"""Small geometry helpers: boxes along a wall line, rectangles with holes, extruded prisms."""

from app.geometry.rect import Rect
from app.models.common import Axis
from app.scene.model import Box3, MeshData

EPS = 1e-4


def wall_box(axis: Axis, coord: float, half_depth: float, a: float, b: float, z0: float, z1: float) -> Box3:
    """A box spanning [a, b] along a wall line at `coord`, `half_depth` either side of it."""
    if axis is Axis.X:
        return Box3(min=(round(a, 4), round(coord - half_depth, 4), round(z0, 4)), max=(round(b, 4), round(coord + half_depth, 4), round(z1, 4)))
    return Box3(min=(round(coord - half_depth, 4), round(a, 4), round(z0, 4)), max=(round(coord + half_depth, 4), round(b, 4), round(z1, 4)))


def subtract(rect: Rect, holes: list[Rect]) -> list[Rect]:
    """`rect` minus every hole, as non-overlapping rectangles."""
    pieces = [rect]
    for hole in holes:
        next_pieces = []
        for r in pieces:
            if r.intersection_area(hole) <= EPS:
                next_pieces.append(r)
                continue
            x0, x1 = max(r.x, hole.x), min(r.x2, hole.x2)
            y0, y1 = max(r.y, hole.y), min(r.y2, hole.y2)
            candidates = [
                Rect(r.x, r.y, x0 - r.x, r.depth),       # left strip, full depth
                Rect(x1, r.y, r.x2 - x1, r.depth),       # right strip, full depth
                Rect(x0, r.y, x1 - x0, y0 - r.y),        # in front of the hole
                Rect(x0, y1, x1 - x0, r.y2 - y1),        # behind the hole
            ]
            next_pieces += [c for c in candidates if c.width > EPS and c.depth > EPS]
        pieces = next_pieces
    return pieces


def rect_box(r: Rect, z0: float, z1: float) -> Box3:
    return Box3(min=(round(r.x, 4), round(r.y, 4), round(z0, 4)), max=(round(r.x2, 4), round(r.y2, 4), round(z1, 4)))


def prism(profile: list[tuple[float, float]], u0: float, u1: float, ridge: Axis) -> MeshData:
    """Extrude a (v, z) polygon, listed anticlockwise, from u0 to u1 along the ridge axis.

    Local axes are u (along the ridge), v (across it), z (up). With the ridge along Y the
    mapping to world axes is a mirror image, so faces are reversed to keep normals outward."""
    n = len(profile)
    local = [(u0, v, z) for v, z in profile] + [(u1, v, z) for v, z in profile]
    faces = [list(reversed(range(n))), [n + i for i in range(n)]]
    faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return to_world(local, faces, ridge)


def to_world(local: list[tuple[float, float, float]], faces: list[list[int]], ridge: Axis) -> MeshData:
    if ridge is Axis.X:
        vertices = [(u, v, z) for u, v, z in local]
    else:
        vertices = [(v, u, z) for u, v, z in local]
        faces = [list(reversed(f)) for f in faces]
    return MeshData(vertices=[tuple(round(c, 4) for c in vtx) for vtx in vertices], faces=faces)  # type: ignore[misc]
