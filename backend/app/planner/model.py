"""Working data structures used while a plan is being built."""

from dataclasses import dataclass, field

from app.geometry.rect import Rect
from app.models.room import RoomType


@dataclass
class Box:
    """A room being planned. `rect` is filled in once the layout is decided."""

    id: str
    name: str
    type: RoomType
    floor: int
    target_area: float
    glazing: str = "standard"
    preferred_side: str = "any"
    synthetic: bool = False
    rect: Rect | None = None

    @property
    def area(self) -> float:
        return self.rect.area if self.rect else 0.0


@dataclass
class Row:
    """One slice of a column, front to rear: a main room plus any rooms that hang off it."""

    main: Box
    children: list[Box] = field(default_factory=list)
    children_inline: bool = False  # True: children share the row beside the main room
    is_child: bool = False  # a child room given its own row; reached through its parent, not the spine

    @property
    def area(self) -> float:
        return self.main.target_area + sum(c.target_area for c in self.children)


@dataclass
class FloorZones:
    level: int
    spine: Box
    slot: Box | None = None  # small room at the rear end of the spine
    left: list[Row] = field(default_factory=list)
    right: list[Row] = field(default_factory=list)

    def boxes(self) -> list[Box]:
        result = [self.spine] + ([self.slot] if self.slot else [])
        for row in self.left + self.right:
            result += [row.main, *row.children]
        return result


@dataclass
class StairPlan:
    from_floor: int
    side: str  # against the spine's "left" or "right" wall, or "centre", "centre_left", "centre_right"
    x: float
    y: float
    width: float
    risers: int
    rise: float
    run: float

    @property
    def length(self) -> float:
        return self.run * (self.risers - 1)

    @property
    def footprint(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.length)
