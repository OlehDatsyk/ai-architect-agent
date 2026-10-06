"""Wall runs for one floor, derived from the room rectangles.

Conventions (no two wall boxes overlap):
- Walls are centred on room boundary lines.
- Exterior: front and rear walls run the full outer width and own the corners; left and
  right walls fit between them.
- Interior: collinear shared edges are merged into runs. Runs along X own every junction
  square; runs along Y are cut back around them. Interior runs stop at the inner face of
  the exterior walls.
"""

from collections import defaultdict
from dataclasses import dataclass

from app.geometry.rect import Rect, shared_segment
from app.models.common import Axis, Side

TOL = 0.005


@dataclass(frozen=True)
class WallRun:
    """A straight wall in plan: along `axis` at constant `coord`, from `start` to `end`."""

    axis: Axis
    coord: float
    start: float
    end: float
    thickness: float
    side: Side | None = None  # exterior walls only

    @property
    def length(self) -> float:
        return self.end - self.start

    def plan_rect(self) -> Rect:
        half = self.thickness / 2
        if self.axis is Axis.X:
            return Rect(self.start, self.coord - half, self.length, self.thickness)
        return Rect(self.coord - half, self.start, self.thickness, self.length)


def exterior_runs(width: float, depth: float, thickness: float) -> list[WallRun]:
    h = thickness / 2
    return [
        WallRun(Axis.X, 0.0, -h, width + h, thickness, Side.FRONT),
        WallRun(Axis.X, depth, -h, width + h, thickness, Side.REAR),
        WallRun(Axis.Y, 0.0, h, depth - h, thickness, Side.LEFT),
        WallRun(Axis.Y, width, h, depth - h, thickness, Side.RIGHT),
    ]


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1] + TOL:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def interior_lines(rooms: list[Rect]) -> list[tuple[Axis, float, float, float]]:
    """Maximal collinear stretches of wall shared by two rooms: (axis, coord, start, end)."""
    by_line: dict[tuple[Axis, float], list[tuple[float, float]]] = defaultdict(list)
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            seg = shared_segment(a, b)
            if seg is not None:
                by_line[(seg.axis, round(seg.coord, 3))].append((seg.start, seg.end))
    return [(axis, coord, s, e) for (axis, coord), spans in sorted(by_line.items()) for s, e in _merge(spans)]


def interior_runs(rooms: list[Rect], width: float, depth: float, ext: float, thickness: float) -> list[WallRun]:
    lines = interior_lines(rooms)
    half_ext, half = ext / 2, thickness / 2
    limits = {Axis.X: width, Axis.Y: depth}

    def at_perimeter(value: float, axis: Axis) -> bool:
        return abs(value) <= TOL or abs(value - limits[axis]) <= TOL

    x_lines = [(c, s, e) for axis, c, s, e in lines if axis is Axis.X]
    y_lines = [(c, s, e) for axis, c, s, e in lines if axis is Axis.Y]
    runs: list[WallRun] = []

    # X runs: stop at exterior inner faces; extend half a thickness into any junction they end at.
    for coord, start, end in x_lines:
        new_start, new_end = start, end
        if at_perimeter(start, Axis.X):
            new_start = half_ext
        elif any(abs(yc - start) <= TOL and ys - TOL <= coord <= ye + TOL for yc, ys, ye in y_lines):
            new_start = start - half
        if at_perimeter(end, Axis.X):
            new_end = limits[Axis.X] - half_ext
        elif any(abs(yc - end) <= TOL and ys - TOL <= coord <= ye + TOL for yc, ys, ye in y_lines):
            new_end = end + half
        runs.append(WallRun(Axis.X, coord, round(new_start, 4), round(new_end, 4), thickness))

    # Y runs: stop at exterior inner faces; cut back around every X run they meet.
    for coord, start, end in y_lines:
        lo = half_ext if at_perimeter(start, Axis.Y) else start
        hi = limits[Axis.Y] - half_ext if at_perimeter(end, Axis.Y) else end
        cuts = sorted(
            xc for xc, xs, xe in x_lines
            if xs - TOL <= coord <= xe + TOL and start - TOL <= xc <= end + TOL
        )
        pieces, cursor = [], lo
        for c in cuts:
            if c - half > cursor + TOL:
                pieces.append((cursor, c - half))
            cursor = max(cursor, c + half)
        if hi > cursor + TOL:
            pieces.append((cursor, hi))
        runs += [WallRun(Axis.Y, coord, round(a, 4), round(b, 4), thickness) for a, b in pieces]
    return runs
