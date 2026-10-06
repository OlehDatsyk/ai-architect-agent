"""Things that would collide with real wall thickness in 3D.

Most rules treat walls as lines on room boundaries. These use the same wall runs as the
3D scene (centred on boundaries, 0.3 m exterior / 0.1 m interior by default) so the 2D
specification and the Blender model cannot disagree.
"""

from collections.abc import Iterator

from app.geometry.placement import door_segment, window_segment
from app.geometry.rect import Rect, Segment
from app.geometry.stairs import stair_footprint
from app.scene.walls import TOL, WallRun, exterior_runs, interior_runs
from app.validation.context import ValidationContext
from app.validation.report import ValidationIssue, error

AREA_TOL = 1e-4


def _runs(ctx: ValidationContext, level: int) -> list[WallRun]:
    b = ctx.spec.building
    rects = [ctx.room_rect(r) for r in ctx.spec.rooms_on_floor(level)]
    return exterior_runs(b.width, b.depth, b.wall_thickness) + interior_runs(rects, b.width, b.depth, b.wall_thickness, b.interior_wall_thickness)


def _opening_hits_wall(segment: Segment, runs: list[WallRun]) -> bool:
    """An opening sits in its own wall; it must not run into a wall that crosses or meets it."""
    thin = (Rect(segment.start, segment.coord - 0.001, segment.length, 0.002) if segment.axis.value == "x"
            else Rect(segment.coord - 0.001, segment.start, 0.002, segment.length))
    for run in runs:
        if run.axis is segment.axis and abs(run.coord - segment.coord) <= TOL:
            continue  # the wall the opening is in
        if run.plan_rect().intersection_area(thin) > AREA_TOL * 0.002:
            return True
    return False


def check_stairs_clear_walls(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    for stair in ctx.spec.stairs:
        footprint = stair_footprint(stair)
        for level, what in ((stair.from_floor, "runs into"), (stair.to_floor, "needs a stairwell through")):
            if level not in ctx.floors:
                continue
            if any(run.plan_rect().intersection_area(footprint) > AREA_TOL for run in _runs(ctx, level)):
                yield error("stair_hits_wall", f"Stair {stair.id} {what} a wall on {ctx.floor_name(level)}; move it clear of the wall thickness.", stair.id)


def check_openings_clear_walls(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    runs_by_floor = {level: _runs(ctx, level) for level in ctx.floors}
    for door in ctx.spec.doors:
        if door.floor in runs_by_floor and _opening_hits_wall(door_segment(door), runs_by_floor[door.floor]):
            yield error("opening_hits_wall", f"Door {door.id} runs into the thickness of a neighbouring wall; move it away from the corner.", door.id)
    for window in ctx.spec.windows:
        room = ctx.rooms.get(window.room)
        if room and room.floor in runs_by_floor and _opening_hits_wall(window_segment(window, ctx.footprint), runs_by_floor[room.floor]):
            yield error("opening_hits_wall", f"Window {window.id} runs into the thickness of a neighbouring wall; move it away from the corner.", window.id)
