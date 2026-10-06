"""The arrangement of an existing plan, read back from its specification, so that a modified
design can keep everything the modification does not need to change."""

from dataclasses import dataclass, field

from app.geometry.stairs import stair_footprint
from app.models.building import BuildingSpecification
from app.models.room import RoomType

SPINE_TYPES = (RoomType.ENTRANCE, RoomType.HALLWAY, RoomType.LANDING)


@dataclass
class LayoutAnchor:
    spine_x: float
    spine_width: float
    two_columns: bool
    central: bool
    sides: dict[str, int] = field(default_factory=dict)      # room id -> 0 (left of the spine) or 1 (right)
    positions: dict[str, float] = field(default_factory=dict)  # room id -> distance from the front (order)


def anchor_from(spec: BuildingSpecification) -> LayoutAnchor | None:
    """None when the specification does not have the spine-and-columns shape the planner makes."""
    ground = spec.rooms_on_floor(0)
    spine = None
    if spec.stairs:
        fp = stair_footprint(spec.stairs[0])
        spine = next((r for r in ground if r.x - 0.01 <= fp.x and fp.x + fp.width <= r.x + r.width + 0.01
                      and r.y - 0.01 <= fp.y and fp.y + fp.depth <= r.y + r.depth + 0.01), None)
    if spine is None:
        candidates = [r for r in ground if r.type in SPINE_TYPES and r.y <= 0.01]
        spine = max(candidates, key=lambda r: r.depth, default=None)
    if spine is None:
        return None
    left_edge, right_edge = spine.x, spine.x + spine.width
    anchor = LayoutAnchor(spine_x=round(left_edge, 2), spine_width=round(spine.width, 2),
                          two_columns=left_edge > 0.01, central=False)
    if spec.stairs:
        fp = stair_footprint(spec.stairs[0])
        anchor.central = abs((fp.x + fp.width / 2) - (left_edge + spine.width / 2)) < 0.15
    for room in spec.rooms:
        if room.x + room.width <= left_edge + 0.01:
            anchor.sides[room.id] = 0
        elif room.x >= right_edge - 0.01:
            anchor.sides[room.id] = 1
        else:
            continue  # the spine, or the small room behind it
        anchor.positions[room.id] = room.y
    return anchor
