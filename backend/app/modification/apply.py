"""Applying a ChangeSet: layout operations edit the design intent; finishing operations become
overrides re-applied after every re-plan. realise() turns intent + overrides into a specification."""

from dataclasses import dataclass

from app.geometry.placement import door_segment, exterior_side_of, window_segment
from app.geometry.rect import Rect, edge, exterior_sides
from app.models.building import BuildingSpecification
from app.models.common import Side
from app.models.intent import DesignConstraints, DesignIntent, IntentConnection, IntentRoom
from app.models.materials import MATERIAL_USES, MaterialRef, MaterialUse
from app.models.opening import Window, WindowStyle
from app.models.roof import RoofType
from app.modification.changeset import (
    AddBalcony,
    AddRoom,
    AddWindow,
    Op,
    Override,
    RemoveBalcony,
    RemoveRoom,
    RemoveWindow,
    RenameRoom,
    SetExteriorMaterial,
    SetRoof,
    SetRoomArea,
    SetRoomFinish,
    SetRoomGlazing,
    SetRoomSide,
    SetRoomWidth,
)
from app.planner import plan_building
from app.planner.anchor import LayoutAnchor
from app.planner.layout import place_in_free_space
from app.validation import ValidationReport, validate_specification
from app.validation.intent import validate_intent

CORNER_CLEARANCE = 0.4  # keep added windows this far from the room's corners (wall thickness + reveal)
COMFORTABLE_COLUMN = 3.0  # a width change may take space from the other side only if its rooms stay this wide
WINDOW_SIZES = {  # size -> (width, height, sill)
    "standard": (1.2, 1.3, 0.9),
    "large": (2.0, 1.6, 0.6),
    "floor_to_ceiling": (1.8, None, 0.0),
}
SURFACE_USE = {
    "wall": MaterialUse.EXTERIOR_WALL, "accent": MaterialUse.EXTERIOR_WALL,
    "trim": MaterialUse.JOINERY, "window_frame": MaterialUse.JOINERY, "door": MaterialUse.JOINERY,
}


class ModificationError(ValueError):
    """An operation that cannot be applied to this design, worded for the user (and for Claude)."""


# ----------------------------------------------------------------------------- checking

def check_operation(op: Op, intent: DesignIntent, spec: BuildingSpecification) -> None:
    rooms = {r.id: r for r in intent.rooms}
    stair_rooms = {s.start_room for s in intent.stairs} | {s.arrival_room for s in intent.stairs}

    def room(room_id: str):
        if room_id not in rooms:
            raise ModificationError(f"There is no room '{room_id}'. Rooms are: {', '.join(sorted(rooms))}.")
        return rooms[room_id]

    if isinstance(op, (SetRoomArea, SetRoomWidth, RenameRoom, SetRoomSide, SetRoomGlazing, SetRoomFinish, AddWindow)):
        room(op.room_id)
    if isinstance(op, RemoveRoom):
        room(op.room_id)
        if op.room_id == intent.entrance_room or op.room_id in stair_rooms:
            raise ModificationError(f"{rooms[op.room_id].name} holds the entrance or the stairs and cannot be removed.")
    if isinstance(op, AddRoom):
        if op.room_id in rooms:
            raise ModificationError(f"A room with ID '{op.room_id}' already exists; choose a new ID.")
        target = room(op.connect_to)
        if target.floor != op.floor:
            raise ModificationError(f"The new room is on floor {op.floor} but {target.name} is on floor {target.floor}; connect it to a room on the same floor.")
    if isinstance(op, (AddBalcony, RemoveBalcony)):
        if room(op.room_id).floor == 0:
            raise ModificationError(f"{rooms[op.room_id].name} is on the ground floor; balconies are for upper floors.")
    if isinstance(op, RemoveBalcony) and op.room_id not in intent.site.balcony_rooms:
        raise ModificationError(f"{rooms[op.room_id].name} has no balcony to remove.")
    if isinstance(op, SetExteriorMaterial) and SURFACE_USE[op.surface] not in MATERIAL_USES[op.material]:
        raise ModificationError(f"'{op.material.value}' is not suitable for the exterior {op.surface.replace('_', ' ')}.")
    if isinstance(op, SetRoomFinish) and MaterialUse.INTERIOR not in MATERIAL_USES[op.material]:
        raise ModificationError(f"'{op.material.value}' is not an interior finish.")
    if isinstance(op, SetRoof) and op.material is not None and MaterialUse.ROOF not in MATERIAL_USES[op.material]:
        raise ModificationError(f"'{op.material.value}' is not a roofing material.")
    if isinstance(op, RemoveWindow) and op.window_id not in {w.id for w in spec.windows}:
        raise ModificationError(f"There is no window '{op.window_id}'.")


# ----------------------------------------------------------------------------- layout operations

def apply_layout(op: Op, intent: DesignIntent, anchor: LayoutAnchor | None = None,
                 current: BuildingSpecification | None = None) -> None:
    rooms = {r.id: r for r in intent.rooms}
    if isinstance(op, SetRoomWidth):
        # A room spans its side of the house, so its width is set by where the hall (spine) runs.
        # Take the space from the other side if those rooms stay comfortably wide; otherwise extend
        # the building by the difference, as a real extension would.
        side = anchor.sides.get(op.room_id) if anchor else None
        room = next((r for r in current.rooms if r.id == op.room_id), None) if current else None
        if anchor is None or room is None or side is None or not anchor.two_columns:
            raise ModificationError(f"{rooms[op.room_id].name}'s width is fixed by the hall and the outside walls; "
                                    "change its area instead.")
        delta = op.width - room.width
        other = (intent.footprint_width - anchor.spine_x - anchor.spine_width) if side == 0 else anchor.spine_x
        if other - delta < COMFORTABLE_COLUMN:
            intent.footprint_width = round(intent.footprint_width + delta, 2)  # extend the building
            if side == 0:
                anchor.spine_x = round(anchor.spine_x + delta, 2)
        else:
            anchor.spine_x = round(anchor.spine_x + (delta if side == 0 else -delta), 2)
        rooms[op.room_id].target_area = round(op.width * room.depth, 1)
    elif isinstance(op, SetRoomArea):
        rooms[op.room_id].target_area = op.target_area
    elif isinstance(op, RenameRoom):
        rooms[op.room_id].name = op.name
    elif isinstance(op, SetRoomSide):
        rooms[op.room_id].preferred_side = op.side
        if anchor and op.side in ("left", "right") and op.room_id in anchor.sides:
            _swap_sides(op.room_id, 0 if op.side == "left" else 1, intent, anchor)
    elif isinstance(op, SetRoomGlazing):
        rooms[op.room_id].glazing = op.glazing
    elif isinstance(op, AddRoom):
        intent.rooms.append(IntentRoom(id=op.room_id, name=op.name, type=op.type, floor=op.floor,
                                       target_area=op.target_area, glazing="standard", preferred_side="any"))
        intent.connections.append(IntentConnection(room_a=op.connect_to, room_b=op.room_id, kind="door"))
    elif isinstance(op, RemoveRoom):
        intent.rooms = [r for r in intent.rooms if r.id != op.room_id]
        intent.connections = [c for c in intent.connections if op.room_id not in (c.room_a, c.room_b)]
        intent.site.balcony_rooms = [r for r in intent.site.balcony_rooms if r != op.room_id]
    elif isinstance(op, SetRoof):
        if op.type is not None:
            intent.roof.type = op.type
        if op.material is not None:
            intent.roof.material = op.material
        if op.pitch is not None:
            intent.roof.pitch = op.pitch
        elif intent.roof.type is RoofType.FLAT and intent.roof.pitch > 3:
            intent.roof.pitch = 2.0
        elif intent.roof.type is not RoofType.FLAT and intent.roof.pitch < 15:
            intent.roof.pitch = 10.0 if intent.roof.type is RoofType.SHED else 35.0
    elif isinstance(op, AddBalcony):
        if op.room_id not in intent.site.balcony_rooms:
            intent.site.balcony_rooms.append(op.room_id)
    elif isinstance(op, RemoveBalcony):
        intent.site.balcony_rooms = [r for r in intent.site.balcony_rooms if r != op.room_id]


def _swap_sides(room_id: str, new_side: int, intent: DesignIntent, anchor: LayoutAnchor) -> None:
    """Moving a room across the hall: the most similar-sized room on that side (same floor) moves
    the other way, and both keep their front-to-rear positions, so the rest of the plan stays put."""
    old_side = anchor.sides[room_id]
    if old_side == new_side:
        return
    rooms = {r.id: r for r in intent.rooms}
    moving = rooms[room_id]
    partners = [r for r in intent.rooms if r.floor == moving.floor and anchor.sides.get(r.id) == new_side
                and r.preferred_side not in ("left", "right")]
    anchor.sides[room_id] = new_side
    anchor.positions[room_id] = anchor.positions.get(room_id, 0.0) - 0.001  # ahead of a room at the same position
    if partners:
        partner = min(partners, key=lambda r: abs(r.target_area - moving.target_area))
        anchor.sides[partner.id] = old_side


def verify_effects(ops: list[Op], spec: BuildingSpecification, before: BuildingSpecification) -> list[str]:
    """Problems where the re-planned design does not show what an operation asked for."""
    from app.planner.anchor import anchor_from

    problems = []
    rooms = {r.id: r for r in spec.rooms}
    old = {r.id: r for r in before.rooms}
    anchor = anchor_from(spec)
    for op in ops:
        if isinstance(op, SetRoomWidth) and op.room_id in rooms and abs(rooms[op.room_id].width - op.width) > 0.15:
            problems.append(f"{rooms[op.room_id].name} could only be made {rooms[op.room_id].width:.2f} m wide, not {op.width:.2f} m.")
        if isinstance(op, SetRoomArea) and op.room_id in rooms and op.room_id in old:
            wanted_up, got = op.target_area > old[op.room_id].area, rooms[op.room_id].area - old[op.room_id].area
            if abs(op.target_area - old[op.room_id].area) > 0.5 and (got > 0) != wanted_up:
                problems.append(f"{rooms[op.room_id].name} could not be made {'larger' if wanted_up else 'smaller'} by area: the rooms "
                                f"beside it fix its depth. Use set_room_width to change it across the house instead.")
        if isinstance(op, SetRoomSide) and op.side in ("left", "right") and anchor and op.room_id in anchor.sides:
            if anchor.sides[op.room_id] != (0 if op.side == "left" else 1):
                problems.append(f"{rooms[op.room_id].name} could not be moved to the {op.side} side.")
        if isinstance(op, AddBalcony) and not any(b.room == op.room_id for b in spec.balconies):
            problems.append(f"{rooms[op.room_id].name if op.room_id in rooms else op.room_id} has no exterior wall long enough for a balcony.")
    return problems


# ----------------------------------------------------------------------------- overrides

def apply_override(op: Op, spec: BuildingSpecification) -> str | None:
    """Apply one finishing operation in place. Returns a note if it no longer applies."""
    rooms = {r.id: r for r in spec.rooms}
    if isinstance(op, SetExteriorMaterial):
        setattr(spec.exterior, f"{op.surface}_material", MaterialRef(id=op.material, colour=op.colour))
    elif isinstance(op, SetRoomFinish):
        if op.room_id not in rooms:
            return f"A {op.surface} finish for '{op.room_id}' was dropped because that room no longer exists."
        setattr(rooms[op.room_id], f"{op.surface}_material", MaterialRef(id=op.material, colour=op.colour))
    elif isinstance(op, RemoveWindow):
        if not any(w.id == op.window_id for w in spec.windows):
            return f"Window '{op.window_id}' was already gone after re-planning, so removing it had no effect."
        spec.windows = [w for w in spec.windows if w.id != op.window_id]
    elif isinstance(op, AddWindow):
        if op.room_id not in rooms:
            return f"A window for '{op.room_id}' was dropped because that room no longer exists."
        spec.windows.append(place_window(spec, op))
    return None


def place_window(spec: BuildingSpecification, op: AddWindow) -> Window:
    """A new window on free exterior wall of the room, clear of corners and other openings."""
    room = next(r for r in spec.rooms if r.id == op.room_id)
    footprint = Rect(0, 0, spec.building.width, spec.building.depth)
    rect = Rect(room.x, room.y, room.width, room.depth)
    sides = exterior_sides(rect, footprint)
    if not sides:
        raise ModificationError(f"{room.name} has no exterior wall, so it cannot have a window.")
    if op.side != "any":
        if Side(op.side) not in sides:
            raise ModificationError(f"{room.name} does not touch the {op.side} wall; its exterior walls are: "
                                    f"{', '.join(s.value for s in sides)}.")
        sides = [Side(op.side)]
    else:
        sides = sorted(sides, key=lambda s: -edge(rect, s).length)

    floor = spec.floor(room.floor)
    ceiling = room.height or ((floor.height if floor else 2.7) - spec.building.slab_thickness)
    width, height, sill = WINDOW_SIZES[op.size]
    height = ceiling - 0.3 if height is None else min(height, ceiling - sill - 0.15)
    floor_rooms = {r.id for r in spec.rooms if r.floor == room.floor}
    def used_on(side: Side) -> list[tuple[float, float]]:
        used = [(s.start, s.end) for w in spec.windows if w.room in floor_rooms and w.wall is side
                for s in [window_segment(w, footprint)]]
        used += [(s.start, s.end) for d in spec.doors if d.is_external and d.floor == room.floor
                 for s in [door_segment(d)] if exterior_side_of(s, footprint) is side]
        return used

    # The full width on any wall before a narrower window on the first.
    for attempt in (width, width * 0.75, width * 0.5):
        if attempt < 0.6:
            break
        for side in sides:
            wall = edge(rect, side)
            centre = place_in_free_space(wall.start, wall.end, round(attempt, 2), used_on(side), margin=CORNER_CLEARANCE)
            if centre is not None:
                taken = {w.id for w in spec.windows}
                base, n = f"win_{room.id}_{side.value}_added"[:60], 1
                while f"{base}_{n}" in taken:
                    n += 1
                return Window(id=f"{base}_{n}", room=room.id, wall=side, offset=centre, width=round(attempt, 2),
                              height=round(height, 2), sill_height=sill,
                              style=WindowStyle.FLOOR_TO_CEILING if op.size == "floor_to_ceiling" else WindowStyle.CASEMENT)
    raise ModificationError(f"There is no free wall space for another window in {room.name}.")


# ----------------------------------------------------------------------------- realising a design

@dataclass
class Realised:
    specification: BuildingSpecification
    report: ValidationReport
    notes: list[str]


def realise(intent: DesignIntent, overrides: list[Override], anchor: LayoutAnchor | None = None) -> Realised:
    """intent -> planned specification (keeping `anchor`'s arrangement where possible) ->
    overrides applied in order -> validated."""
    errors = [i for i in validate_intent(intent, DesignConstraints()).issues if i.severity.value == "error"]
    if errors:
        raise ModificationError(" ".join(i.message for i in errors[:5]))
    planned = plan_building(intent, anchor)
    spec = planned.specification.model_copy(deep=True)
    notes = list(planned.notes)
    for override in overrides:
        note = apply_override(override.typed(), spec)
        if note:
            notes.append(note)
    result = validate_specification(spec)
    return Realised(specification=result.specification or spec, report=result.report, notes=notes)
