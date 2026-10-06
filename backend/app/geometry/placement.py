"""Where doors, windows and balconies sit, as wall segments."""

from app.geometry.rect import TOLERANCE, Rect, Segment, edge
from app.models.common import Axis, Side
from app.models.opening import Balcony, Door, Window

SIDE_AXIS = {Side.FRONT: Axis.X, Side.REAR: Axis.X, Side.LEFT: Axis.Y, Side.RIGHT: Axis.Y}


def door_segment(door: Door) -> Segment:
    if door.wall_axis is Axis.X:
        return Segment(Axis.X, door.position.y, door.position.x - door.width / 2, door.position.x + door.width / 2)
    return Segment(Axis.Y, door.position.x, door.position.y - door.width / 2, door.position.y + door.width / 2)


def wall_segment(side: Side, offset: float, width: float, footprint: Rect) -> Segment:
    line = edge(footprint, side)
    return Segment(line.axis, line.coord, offset - width / 2, offset + width / 2)


def window_segment(window: Window, footprint: Rect) -> Segment:
    return wall_segment(window.wall, window.offset, window.width, footprint)


def balcony_segment(balcony: Balcony, footprint: Rect) -> Segment:
    return wall_segment(balcony.wall, balcony.offset, balcony.width, footprint)


def window_position(window: Window, footprint: Rect) -> tuple[float, float]:
    """Centre of the window on the wall line, in plan coordinates."""
    segment = window_segment(window, footprint)
    middle = (segment.start + segment.end) / 2
    return (middle, segment.coord) if segment.axis is Axis.X else (segment.coord, middle)


def exterior_side_of(segment: Segment, footprint: Rect, tol: float = TOLERANCE) -> Side | None:
    """Which exterior wall a segment lies on, if any."""
    for side in Side:
        line = edge(footprint, side)
        if segment.is_on_line(line.axis, line.coord, tol):
            return side
    return None
