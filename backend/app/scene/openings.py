"""Wall openings, and the doors and windows that fill them.

A wall with openings becomes solid pieces: full-height pieces between openings, a lintel
above each opening and a sill wall below each window. Doors and windows sit inside the
opening, so nothing overlaps the wall.
"""

from dataclasses import dataclass

from app.geometry.placement import door_segment, exterior_side_of, window_segment
from app.geometry.rect import Rect
from app.models.building import BuildingSpecification
from app.models.opening import Door, DoorType, Window, WindowStyle
from app.scene.model import Box3
from app.scene.shapes import EPS, wall_box
from app.scene.walls import TOL, WallRun

FRAME = 0.05          # door frame member width
WINDOW_FRAME = 0.06
LEAF = 0.04           # door leaf thickness
GLASS = 0.02
MULLION_ABOVE = 1.4   # windows wider than this get a centre mullion


@dataclass(frozen=True)
class Opening:
    start: float
    end: float
    z0: float
    z1: float
    source: Door | Window


def openings_for_run(run: WallRun, spec: BuildingSpecification, level: int, e: float, wall_top: float) -> list[Opening]:
    footprint = Rect(0, 0, spec.building.width, spec.building.depth)
    room_floor = {r.id: r.floor for r in spec.rooms}
    found: list[Opening] = []

    def on_run(axis, coord: float, a: float, b: float) -> bool:
        return axis is run.axis and abs(coord - run.coord) <= TOL and a >= run.start - TOL and b <= run.end + TOL

    for door in spec.doors:
        if door.floor != level or door.is_external != (run.side is not None):
            continue
        seg = door_segment(door)
        if run.side is not None and exterior_side_of(seg, footprint) is not run.side:
            continue
        if on_run(seg.axis, seg.coord, seg.start, seg.end):
            top = wall_top if door.type is DoorType.OPENING else e + door.height
            found.append(Opening(seg.start, seg.end, e, min(top, wall_top), door))
    if run.side is not None:
        for window in spec.windows:
            if room_floor.get(window.room) != level or window.wall is not run.side:
                continue
            seg = window_segment(window, footprint)
            z0 = e + window.sill_height
            found.append(Opening(seg.start, seg.end, z0, min(z0 + window.height, wall_top), window))
    return sorted(found, key=lambda o: o.start)


def wall_pieces(run: WallRun, z_bottom: float, z_top: float, openings: list[Opening]) -> list[Box3]:
    half = run.thickness / 2
    pieces: list[Box3] = []
    cursor = run.start
    for op in openings:
        a, b = max(op.start, run.start), min(op.end, run.end)
        if a > cursor + EPS:
            pieces.append(wall_box(run.axis, run.coord, half, cursor, a, z_bottom, z_top))
        a = max(a, cursor)
        if b > a + EPS:
            if op.z1 < z_top - EPS:
                pieces.append(wall_box(run.axis, run.coord, half, a, b, op.z1, z_top))
            if op.z0 > z_bottom + EPS:
                pieces.append(wall_box(run.axis, run.coord, half, a, b, z_bottom, op.z0))
        cursor = max(cursor, b)
    if run.end > cursor + EPS:
        pieces.append(wall_box(run.axis, run.coord, half, cursor, run.end, z_bottom, z_top))
    return pieces


def door_parts(op: Opening, run: WallRun) -> tuple[list[Box3], list[Box3]]:
    """(frame boxes, leaf boxes). A doorless opening has neither."""
    door = op.source
    assert isinstance(door, Door)
    if door.type is DoorType.OPENING:
        return [], []
    half = run.thickness / 2
    a, b, z0, z1 = op.start, op.end, op.z0, op.z1
    frame = [
        wall_box(run.axis, run.coord, half, a, a + FRAME, z0, z1),
        wall_box(run.axis, run.coord, half, b - FRAME, b, z0, z1),
        wall_box(run.axis, run.coord, half, a + FRAME, b - FRAME, z1 - FRAME, z1),
    ]
    if door.type is DoorType.PATIO_SLIDING:  # two sliding panels, slightly offset
        mid = (a + b) / 2
        leaf = [
            wall_box(run.axis, run.coord - LEAF / 2, LEAF / 2, a + FRAME, mid + 0.02, z0 + 0.01, z1 - FRAME),
            wall_box(run.axis, run.coord + LEAF / 2, LEAF / 2, mid - 0.02, b - FRAME, z0 + 0.01, z1 - FRAME),
        ]
    else:
        leaf = [wall_box(run.axis, run.coord, LEAF / 2, a + FRAME, b - FRAME, z0 + 0.01, z1 - FRAME)]
    return frame, leaf


def window_parts(op: Opening, run: WallRun) -> tuple[list[Box3], list[Box3]]:
    """(frame boxes, glass boxes)."""
    window = op.source
    assert isinstance(window, Window)
    half = min(0.05, run.thickness / 2)
    a, b, z0, z1 = op.start, op.end, op.z0, op.z1
    f = WINDOW_FRAME
    frame = [
        wall_box(run.axis, run.coord, half, a, a + f, z0, z1),
        wall_box(run.axis, run.coord, half, b - f, b, z0, z1),
        wall_box(run.axis, run.coord, half, a + f, b - f, z1 - f, z1),
        wall_box(run.axis, run.coord, half, a + f, b - f, z0, z0 + f),
    ]
    panes = [(a + f, b - f)]
    if b - a > MULLION_ABOVE and window.style is not WindowStyle.FIXED:
        mid = (a + b) / 2
        frame.append(wall_box(run.axis, run.coord, half, mid - f / 2, mid + f / 2, z0 + f, z1 - f))
        panes = [(a + f, mid - f / 2), (mid + f / 2, b - f)]
    glass = [wall_box(run.axis, run.coord, GLASS / 2, p, q, z0 + f, z1 - f) for p, q in panes]
    return frame, glass
