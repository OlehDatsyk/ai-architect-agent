"""Ordered list of validation rules. Each rule is a pure function: context -> issues."""

from collections.abc import Callable, Iterable

from app.validation.context import ValidationContext
from app.validation.report import ValidationIssue
from app.validation.rules import circulation, clearance, openings, roof, rooms, site, structure

Rule = Callable[[ValidationContext], Iterable[ValidationIssue]]

ALL_RULES: tuple[Rule, ...] = (
    structure.check_duplicate_ids,
    structure.check_floors,
    structure.check_building_dimensions,
    rooms.check_room_floors,
    rooms.check_rooms_inside_footprint,
    rooms.check_room_overlaps,
    rooms.check_room_sizes,
    rooms.check_room_heights,
    rooms.check_upper_floor_support,
    rooms.check_materials,
    openings.check_door_references,
    openings.check_door_placement,
    openings.check_door_heights,
    openings.check_upper_floor_external_doors,
    openings.check_windows,
    openings.check_exterior_opening_clashes,
    openings.check_habitable_rooms_have_windows,
    openings.check_balconies,
    circulation.check_entrance,
    circulation.check_stairs,
    circulation.check_floors_connected,
    circulation.check_rooms_reachable,
    circulation.check_kitchen_access,
    clearance.check_stairs_clear_walls,
    clearance.check_openings_clear_walls,
    roof.check_roof,
    site.check_site,
    site.check_planting_clearance,
)
