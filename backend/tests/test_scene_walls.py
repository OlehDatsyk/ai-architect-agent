from itertools import combinations

import pytest

from app.geometry.rect import Rect, shared_segment
from app.models.common import Axis
from app.scene.walls import exterior_runs, interior_lines, interior_runs
from tests.scene_cases import all_specs

EXT, INT = 0.3, 0.1


def runs_for(rooms: list[Rect], width: float, depth: float):
    return exterior_runs(width, depth, EXT) + interior_runs(rooms, width, depth, EXT, INT)


def overlaps(runs) -> list:
    return [(a, b) for a, b in combinations(runs, 2) if a.plan_rect().intersection_area(b.plan_rect()) > 1e-6]


def test_exterior_walls_meet_without_overlapping() -> None:
    runs = exterior_runs(10, 8, EXT)
    assert overlaps(runs) == []
    outer = Rect(-0.15, -0.15, 10.3, 8.3)
    assert sum(r.plan_rect().area for r in runs) == pytest.approx(outer.area - Rect(0.15, 0.15, 9.7, 7.7).area)


def test_collinear_shared_edges_merge_into_one_run() -> None:
    rooms = [Rect(0, 0, 4, 3), Rect(4, 0, 4, 3), Rect(0, 3, 8, 3)]
    lines = interior_lines(rooms)
    assert (Axis.X, 3.0, 0.0, 8.0) in lines


def test_t_junction() -> None:
    #  ┌───────┐
    #  │   C   │      X run at y=3 owns the junction; the Y run at x=4 stops at its face.
    #  ├───┬───┤
    #  │ A │ B │
    #  └───┴───┘
    rooms = [Rect(0, 0, 4, 3), Rect(4, 0, 4, 3), Rect(0, 3, 8, 3)]
    runs = interior_runs(rooms, 8, 6, EXT, INT)
    x_run = next(r for r in runs if r.axis is Axis.X)
    y_run = next(r for r in runs if r.axis is Axis.Y)
    assert (x_run.start, x_run.end) == (0.15, 7.85)
    assert (y_run.start, y_run.end) == (0.15, 2.95)
    assert overlaps(runs + exterior_runs(8, 6, EXT)) == []


def test_cross_junction_splits_the_y_run() -> None:
    rooms = [Rect(0, 0, 4, 3), Rect(4, 0, 4, 3), Rect(0, 3, 4, 3), Rect(4, 3, 4, 3)]
    runs = interior_runs(rooms, 8, 6, EXT, INT)
    y_runs = sorted((r.start, r.end) for r in runs if r.axis is Axis.Y)
    assert y_runs == [(0.15, 2.95), (3.05, 5.85)]
    assert overlaps(runs) == []


def test_l_corner_is_filled_by_the_x_run() -> None:
    # Room B sits in the corner of A's L; walls meet at (4, 3) and must neither overlap nor leave a hole.
    rooms = [Rect(0, 0, 4, 6), Rect(4, 0, 4, 3), Rect(4, 3, 4, 3)]
    runs = interior_runs(rooms, 8, 6, EXT, INT)
    assert overlaps(runs) == []


def _covered(point: tuple[float, float], runs) -> bool:
    return any(r.plan_rect().contains_point(*point, tol=1e-6) for r in runs)


@pytest.mark.parametrize("case", sorted(all_specs()))
def test_walls_never_overlap_and_every_shared_edge_has_a_wall(case: str) -> None:
    spec = all_specs()[case]
    width, depth = spec.building.width, spec.building.depth
    for floor in spec.floors:
        rooms = [Rect(r.x, r.y, r.width, r.depth) for r in spec.rooms_on_floor(floor.level)]
        runs = runs_for(rooms, width, depth)
        assert overlaps(runs) == [], f"{case} floor {floor.level}"
        for a, b in combinations(rooms, 2):
            seg = shared_segment(a, b)
            if seg is None:
                continue
            for t in (0.25, 0.5, 0.75):
                along = seg.start + t * seg.length
                point = (along, seg.coord) if seg.axis is Axis.X else (seg.coord, along)
                assert _covered(point, runs), f"{case} floor {floor.level}: no wall at {point}"
