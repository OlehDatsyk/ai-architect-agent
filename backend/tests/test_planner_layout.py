import pytest

from app.planner.layout import InfeasibleLayout, cut_points, distribute, free_intervals, place_in_free_space


def test_distribute_is_proportional_when_minimums_are_met() -> None:
    assert distribute([1, 3], [0.5, 0.5], 8) == pytest.approx([2, 6])


def test_distribute_fixes_items_at_their_minimum() -> None:
    result = distribute([0.2, 5, 5], [1.5, 1, 1], 10)
    assert result[0] == pytest.approx(1.5)
    assert sum(result) == pytest.approx(10)
    assert result[1] == pytest.approx(result[2])


def test_distribute_rejects_impossible_minimums() -> None:
    with pytest.raises(InfeasibleLayout):
        distribute([1, 1], [5, 5], 8)


def test_cut_points_end_exactly_at_the_end() -> None:
    points = cut_points([1 / 3, 1 / 3, 1 / 3], 0, 1)
    assert points[0] == 0 and points[-1] == 1 and points == sorted(points)


def test_free_intervals_and_placement() -> None:
    assert free_intervals(0, 10, [(2, 3), (6, 7)]) == [(0, 2), (3, 6), (7, 10)]
    assert place_in_free_space(0, 4, 0.9, [(1, 3.5)], margin=0.15) is None
    centre = place_in_free_space(0, 6, 0.9, [(1, 3.5)], margin=0.15)
    assert centre is not None and centre - 0.45 >= 3.65 - 1e-9 and centre + 0.45 <= 5.85 + 1e-9
