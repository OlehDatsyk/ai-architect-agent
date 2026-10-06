"""Axis-aligned rectangles and wall segments in plan (X/Y)."""

from dataclasses import dataclass

from app.models.common import Axis, Side

# Plan coordinates closer than this are treated as equal (1 cm).
TOLERANCE = 0.01
# Differences below this are floating-point noise (e.g. 5.2 + 4.4 = 9.600000000000001).
EPSILON = 1e-6


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    depth: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.depth

    @property
    def area(self) -> float:
        return self.width * self.depth

    def intersection_area(self, other: "Rect") -> float:
        dx = min(self.x2, other.x2) - max(self.x, other.x)
        dy = min(self.y2, other.y2) - max(self.y, other.y)
        return dx * dy if dx > 0 and dy > 0 else 0.0

    def contains_rect(self, other: "Rect", tol: float = TOLERANCE) -> bool:
        return (
            other.x >= self.x - tol and other.y >= self.y - tol
            and other.x2 <= self.x2 + tol and other.y2 <= self.y2 + tol
        )

    def contains_point(self, px: float, py: float, tol: float = TOLERANCE) -> bool:
        return self.x - tol <= px <= self.x2 + tol and self.y - tol <= py <= self.y2 + tol

    def overhang(self, outer: "Rect") -> dict[Side, float]:
        """How far this rectangle extends beyond each side of `outer` (only positive values)."""
        amounts = {
            Side.LEFT: outer.x - self.x,
            Side.FRONT: outer.y - self.y,
            Side.RIGHT: self.x2 - outer.x2,
            Side.REAR: self.y2 - outer.y2,
        }
        return {side: amount for side, amount in amounts.items() if amount > EPSILON}


@dataclass(frozen=True)
class Segment:
    """A straight wall segment. axis X: runs along X at constant y = coord. axis Y: the reverse."""

    axis: Axis
    coord: float
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start

    def is_on_line(self, axis: Axis, coord: float, tol: float = TOLERANCE) -> bool:
        return self.axis == axis and abs(self.coord - coord) <= tol

    def contains_span(self, start: float, end: float, tol: float = TOLERANCE) -> bool:
        return start >= self.start - tol and end <= self.end + tol


def edge(rect: Rect, side: Side) -> Segment:
    if side is Side.FRONT:
        return Segment(Axis.X, rect.y, rect.x, rect.x2)
    if side is Side.REAR:
        return Segment(Axis.X, rect.y2, rect.x, rect.x2)
    if side is Side.LEFT:
        return Segment(Axis.Y, rect.x, rect.y, rect.y2)
    return Segment(Axis.Y, rect.x2, rect.y, rect.y2)


def span_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def shared_segment(a: Rect, b: Rect, tol: float = TOLERANCE) -> Segment | None:
    """The wall segment two touching rectangles share, or None if they share no wall."""
    if abs(a.x2 - b.x) <= tol or abs(b.x2 - a.x) <= tol:
        coord = a.x2 if abs(a.x2 - b.x) <= tol else a.x
        start, end = max(a.y, b.y), min(a.y2, b.y2)
        if end - start > tol:
            return Segment(Axis.Y, coord, start, end)
    if abs(a.y2 - b.y) <= tol or abs(b.y2 - a.y) <= tol:
        coord = a.y2 if abs(a.y2 - b.y) <= tol else a.y
        start, end = max(a.x, b.x), min(a.x2, b.x2)
        if end - start > tol:
            return Segment(Axis.X, coord, start, end)
    return None


def perimeter_segment(footprint: Rect, side: Side) -> Segment:
    return edge(footprint, side)


def exterior_sides(rect: Rect, footprint: Rect, tol: float = TOLERANCE) -> list[Side]:
    """Sides of `rect` that lie on the building's exterior walls."""
    return [
        side for side in Side
        if edge(rect, side).is_on_line(edge(footprint, side).axis, edge(footprint, side).coord, tol)
    ]
