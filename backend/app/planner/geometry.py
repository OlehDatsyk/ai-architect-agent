"""Turns zoned rows into rectangles: two columns either side of a front-to-rear spine."""

from app.geometry.rect import Rect
from app.models.room import RoomType
from app.planner.layout import PRECISION, InfeasibleLayout, cut_points, distribute
from app.planner.model import Box, FloorZones, Row

MIN_COLUMN = 2.6
INLINE_CHILD_MIN_COLUMN = 4.6  # columns at least this wide put en-suites beside their bedroom
MIN_CHILD = 1.2
MIN_MAIN_BESIDE_CHILD = 3.0
SPINE_ACCESS = 1.3  # wall each room shares with the hall or landing: a 0.9 m door plus clearances
MIN_SLOT_SHARE = 0.6  # the rear slot is only used if the room gets at least 60% of its requested area there
MIN_SLOT = 1.2

_MIN_DEPTH = {
    RoomType.GARAGE: 5.0,
    RoomType.WC: 1.2, RoomType.STORAGE: 1.2, RoomType.ENSUITE: 1.2,
    RoomType.BATHROOM: 1.6, RoomType.UTILITY: 1.6,
}
DEFAULT_MIN_DEPTH = 2.4


def min_depth(box: Box) -> float:
    return _MIN_DEPTH.get(box.type, DEFAULT_MIN_DEPTH)


def layout_column(rows: list[Row], x0: float, x1: float, depth: float, exterior_on_left: bool) -> list[Row]:
    """Stack rows front to rear across the full column width and set every room's rect.

    Returns the rows actually used (children may be split out into rows of their own when
    the column is too narrow to put them beside their parent)."""
    width = x1 - x0
    inline = width >= INLINE_CHILD_MIN_COLUMN
    try:
        return _layout(rows, x0, x1, depth, exterior_on_left, inline)
    except InfeasibleLayout:
        if not inline:
            raise
        return _layout(rows, x0, x1, depth, exterior_on_left, inline=False)


def _layout(rows: list[Row], x0: float, x1: float, depth: float, exterior_on_left: bool, inline: bool) -> list[Row]:
    width = x1 - x0
    expanded: list[Row] = []
    for row in rows:
        if row.children and not inline:
            expanded.append(Row(row.main))
            expanded += [Row(child, is_child=True) for child in row.children]
        else:
            expanded.append(Row(row.main, list(row.children), children_inline=bool(row.children)))

    ideal = [r.area / width for r in expanded]
    minimum = [max(min_depth(r.main), MIN_CHILD * len(r.children)) for r in expanded]
    ys = cut_points(distribute(ideal, minimum, depth), 0.0, depth)

    for row, y0, y1 in zip(expanded, ys, ys[1:]):
        row_depth = y1 - y0
        if not row.children_inline:
            row.main.rect = Rect(x0, y0, width, round(row_depth, PRECISION))
            continue
        child_area = sum(c.target_area for c in row.children)
        strip = round(min(max(child_area / row_depth, MIN_CHILD), width - MIN_MAIN_BESIDE_CHILD), PRECISION)
        strip_x = x0 if exterior_on_left else round(x1 - strip, PRECISION)
        main_x = round(x0 + strip, PRECISION) if exterior_on_left else x0
        row.main.rect = Rect(main_x, y0, round(width - strip, PRECISION), round(row_depth, PRECISION))
        child_ys = cut_points(distribute([c.target_area for c in row.children], [MIN_CHILD] * len(row.children), row_depth), y0, y1)
        for child, cy0, cy1 in zip(row.children, child_ys, child_ys[1:]):
            child.rect = Rect(strip_x, cy0, strip, round(cy1 - cy0, PRECISION))
    return expanded


def split_spine(zones: FloorZones, sx: float, sw: float, depth: float, required_depth: float) -> bool:
    """Give the spine its rect, putting the rear-slot room behind it when there is room.
    Returns False if the slot room does not fit (the caller then plans it as a normal room)."""
    rows = zones.left + zones.right
    access = max((r.main.rect.y + SPINE_ACCESS for r in rows if r.main.rect and not r.is_child), default=0.0)
    needed = round(max(required_depth, access, 2.0), PRECISION)
    if zones.slot is None:
        zones.spine.rect = Rect(sx, 0.0, sw, depth)
        return True
    available = depth - needed
    if available < MIN_SLOT or available * sw < zones.slot.target_area * MIN_SLOT_SHARE:
        return False
    slot_depth = round(min(max(zones.slot.target_area / sw, MIN_SLOT), available), PRECISION)
    spine_depth = round(depth - slot_depth, PRECISION)
    zones.spine.rect = Rect(sx, 0.0, sw, spine_depth)
    zones.slot.rect = Rect(sx, spine_depth, sw, round(depth - spine_depth, PRECISION))
    return True

