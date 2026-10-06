"""Lookup tables shared by the validation rules."""

from dataclasses import dataclass, field

from app.geometry.rect import Rect
from app.models.building import BuildingSpecification, Floor
from app.models.room import Room


@dataclass
class ValidationContext:
    spec: BuildingSpecification
    footprint: Rect
    rooms: dict[str, Room] = field(default_factory=dict)
    floors: dict[int, Floor] = field(default_factory=dict)

    @classmethod
    def build(cls, spec: BuildingSpecification) -> "ValidationContext":
        ctx = cls(spec=spec, footprint=Rect(0.0, 0.0, spec.building.width, spec.building.depth))
        for room in spec.rooms:
            ctx.rooms.setdefault(room.id, room)  # duplicates are reported by their own rule
        for floor in spec.floors:
            ctx.floors.setdefault(floor.level, floor)
        return ctx

    def room_rect(self, room: Room) -> Rect:
        return Rect(room.x, room.y, room.width, room.depth)

    def room_height(self, room: Room) -> float | None:
        if room.height is not None:
            return room.height
        floor = self.floors.get(room.floor)
        return None if floor is None else floor.height - self.spec.building.slab_thickness

    def floor_name(self, level: int) -> str:
        floor = self.floors.get(level)
        return floor.name if floor else f"floor {level}"

    def rooms_containing(self, level: int, px: float, py: float) -> list[Room]:
        return [r for r in self.rooms.values() if r.floor == level and self.room_rect(r).contains_point(px, py)]


def fmt(value: float) -> str:
    """Format a measurement for messages: 2 decimal places, no trailing noise."""
    return f"{value:.2f}"
