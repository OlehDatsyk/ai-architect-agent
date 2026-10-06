"""What actually changed between two specifications, in plain English."""

from app.models.building import BuildingSpecification
from app.models.materials import MaterialRef

AREA_CHANGE = 0.3   # m²; smaller differences are rounding
MOVE = 0.05         # m


def _material(ref: MaterialRef | None) -> str:
    if ref is None:
        return "none"
    return ref.id.value.replace("_", " ") + (f" ({ref.colour})" if ref.colour else "")


def describe_changes(old: BuildingSpecification, new: BuildingSpecification) -> list[str]:
    changes: list[str] = []
    old_rooms, new_rooms = {r.id: r for r in old.rooms}, {r.id: r for r in new.rooms}
    for rid in new_rooms.keys() - old_rooms.keys():
        r = new_rooms[rid]
        changes.append(f"Added {r.name} ({r.area:.1f} m²).")
    for rid in old_rooms.keys() - new_rooms.keys():
        changes.append(f"Removed {old_rooms[rid].name}.")
    moved = []
    for rid in sorted(old_rooms.keys() & new_rooms.keys(), key=lambda i: new_rooms[i].name):
        a, b = old_rooms[rid], new_rooms[rid]
        if a.name != b.name:
            changes.append(f"Renamed {a.name} to {b.name}.")
        if abs(a.area - b.area) > AREA_CHANGE:
            changes.append(f"{b.name}: {a.area:.1f} m² -> {b.area:.1f} m² ({b.width:.2f} x {b.depth:.2f} m).")
        elif abs(a.x - b.x) > MOVE or abs(a.y - b.y) > MOVE:
            moved.append(b.name)
        for surface in ("floor", "wall", "ceiling"):
            before, after = getattr(a, f"{surface}_material"), getattr(b, f"{surface}_material")
            if before != after:
                changes.append(f"{b.name} {surface}: {_material(before)} -> {_material(after)}.")
    if moved:
        changes.append(f"Moved to make room: {', '.join(moved)}.")

    old_windows = {w.id: w for w in old.windows}
    new_windows = {w.id: w for w in new.windows}
    names = {**{r.id: r.name for r in old.rooms}, **{r.id: r.name for r in new.rooms}}
    for wid in sorted(new_windows.keys() - old_windows.keys()):
        w = new_windows[wid]
        changes.append(f"Added a {w.width:.1f} m window to {names.get(w.room, w.room)} ({w.wall.value} wall).")
    for wid in sorted(old_windows.keys() - new_windows.keys()):
        w = old_windows[wid]
        changes.append(f"Removed a window from {names.get(w.room, w.room)} ({w.wall.value} wall).")

    for surface in ("wall", "accent", "trim", "window_frame", "door"):
        before, after = getattr(old.exterior, f"{surface}_material"), getattr(new.exterior, f"{surface}_material")
        if before != after:
            changes.append(f"Exterior {surface.replace('_', ' ')}: {_material(before)} -> {_material(after)}.")
    if (old.roof.type, old.roof.pitch, old.roof.material) != (new.roof.type, new.roof.pitch, new.roof.material):
        changes.append(f"Roof: {old.roof.type.value} {old.roof.pitch:g}° {_material(old.roof.material)} -> "
                       f"{new.roof.type.value} {new.roof.pitch:g}° {_material(new.roof.material)}.")
    old_balconies = {b.room for b in old.balconies}
    new_balconies = {b.room for b in new.balconies}
    for rid in new_balconies - old_balconies:
        changes.append(f"Added a balcony to {names.get(rid, rid)}.")
    for rid in old_balconies - new_balconies:
        changes.append(f"Removed the balcony from {names.get(rid, rid)}.")
    return changes
