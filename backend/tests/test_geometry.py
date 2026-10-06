import math

import pytest

from app.geometry.placement import door_segment, exterior_side_of, window_position
from app.geometry.rect import Rect, edge, exterior_sides, shared_segment
from app.geometry.roof import hip_ridge_length, ridge_axis, roof_rise, roof_span
from app.geometry.stairs import MAX_RISE, calculate_stair, stair_arrival_point, stair_footprint, stair_start_point
from app.models import (
    Axis,
    Door,
    DoorType,
    MaterialRef,
    Point2D,
    Roof,
    RoofType,
    Side,
    Stair,
    StairDirection,
    Window,
    WindowStyle,
)


class TestRect:
    def test_intersection_area(self) -> None:
        assert Rect(0, 0, 4, 4).intersection_area(Rect(2, 3, 4, 4)) == pytest.approx(2.0)

    def test_touching_rectangles_do_not_intersect(self) -> None:
        assert Rect(0, 0, 4, 4).intersection_area(Rect(4, 0, 2, 2)) == 0

    def test_overhang_reports_each_side(self) -> None:
        overhang = Rect(-0.5, 1, 11, 2).overhang(Rect(0, 0, 10, 8))
        assert overhang == {Side.LEFT: pytest.approx(0.5), Side.RIGHT: pytest.approx(0.5)}

    def test_overhang_ignores_float_noise(self) -> None:
        assert Rect(5.2, 0, 4.4, 4).overhang(Rect(0, 0, 9.6, 8)) == {}

    def test_shared_segment_vertical_wall(self) -> None:
        seg = shared_segment(Rect(0, 0, 3, 5), Rect(3, 2, 4, 6))
        assert seg is not None
        assert (seg.axis, seg.coord, seg.start, seg.end) == (Axis.Y, 3, 2, 5)

    def test_shared_segment_horizontal_wall(self) -> None:
        seg = shared_segment(Rect(0, 4, 5, 2), Rect(1, 0, 2, 4))
        assert seg is not None and seg.axis is Axis.X and seg.coord == 4 and (seg.start, seg.end) == (1, 3)

    def test_corner_touch_is_not_a_shared_wall(self) -> None:
        assert shared_segment(Rect(0, 0, 2, 2), Rect(2, 2, 2, 2)) is None

    def test_exterior_sides(self) -> None:
        footprint = Rect(0, 0, 10, 8)
        assert set(exterior_sides(Rect(0, 0, 3, 3), footprint)) == {Side.FRONT, Side.LEFT}
        assert exterior_sides(Rect(3, 3, 2, 2), footprint) == []
        assert edge(footprint, Side.REAR).coord == 8


class TestPlacement:
    def test_door_segment_follows_rotation(self) -> None:
        door = Door(id="d", type=DoorType.INTERNAL, floor=0, position=Point2D(x=3, y=2), rotation=90,
                    width=0.9, connects_room_a="a", connects_room_b="b", is_external=False)
        seg = door_segment(door)
        assert seg.axis is Axis.Y and seg.coord == 3 and seg.start == pytest.approx(1.55)

    def test_window_position_on_each_wall(self) -> None:
        footprint = Rect(0, 0, 10, 8)
        def make(side: Side, offset: float) -> Window:
            return Window(id="w", style=WindowStyle.FIXED, room="r", wall=side, offset=offset, width=1, height=1)

        assert window_position(make(Side.FRONT, 4), footprint) == (4, 0)
        assert window_position(make(Side.REAR, 4), footprint) == (4, 8)
        assert window_position(make(Side.RIGHT, 3), footprint) == (10, 3)

    def test_exterior_side_of(self) -> None:
        footprint = Rect(0, 0, 10, 8)
        assert exterior_side_of(edge(Rect(2, 5, 3, 3), Side.REAR), footprint) is Side.REAR
        assert exterior_side_of(edge(Rect(2, 2, 3, 3), Side.REAR), footprint) is None


class TestStairs:
    @pytest.mark.parametrize("height", [2.4, 2.6, 2.7, 2.8, 3.0, 3.4, 4.0])
    def test_calculated_rise_never_exceeds_limit_and_matches_height(self, height: float) -> None:
        dims = calculate_stair(height)
        assert dims.rise <= MAX_RISE
        assert dims.rise * dims.risers == pytest.approx(height)

    def test_typical_house_stair(self) -> None:
        dims = calculate_stair(2.7)
        assert dims.risers == 14
        assert dims.rise == pytest.approx(0.19286, abs=1e-4)
        assert dims.going_length == pytest.approx(13 * 0.25)
        assert dims.pitch_deg < 42

    def test_rejects_non_positive_height(self) -> None:
        with pytest.raises(ValueError):
            calculate_stair(0)

    @pytest.mark.parametrize(
        ("direction", "footprint", "start", "arrival"),
        [
            (StairDirection.FRONT_TO_REAR, (1, 2, 1, 3), (1.5, 2.05), (1.5, 5.1)),
            (StairDirection.REAR_TO_FRONT, (1, 2, 1, 3), (1.5, 4.95), (1.5, 1.9)),
            (StairDirection.LEFT_TO_RIGHT, (1, 2, 3, 1), (1.05, 2.5), (4.1, 2.5)),
            (StairDirection.RIGHT_TO_LEFT, (1, 2, 3, 1), (3.95, 2.5), (0.9, 2.5)),
        ],
    )
    def test_footprint_and_end_points(self, direction, footprint, start, arrival) -> None:
        stair = Stair(id="s", from_floor=0, to_floor=1, x=1, y=2, width=1, direction=direction, risers=13, rise=0.2, run=0.25)
        r = stair_footprint(stair)
        assert (r.x, r.y, r.width, r.depth) == pytest.approx(footprint)
        assert stair_start_point(stair) == pytest.approx(start)
        assert stair_arrival_point(stair) == pytest.approx(arrival)


class TestRoof:
    def roof(self, rtype: RoofType, pitch: float, ridge: Axis | None = None) -> Roof:
        return Roof(type=rtype, pitch=pitch, material=MaterialRef(id="slate"), ridge_direction=ridge)

    def test_flat_roof_has_no_rise(self) -> None:
        assert roof_rise(self.roof(RoofType.FLAT, 2), 10, 8) == 0

    def test_gable_rise_uses_half_span(self) -> None:
        assert roof_rise(self.roof(RoofType.GABLE, 45, Axis.X), 10, 8) == pytest.approx(4.0)

    def test_shed_rise_uses_full_span(self) -> None:
        assert roof_rise(self.roof(RoofType.SHED, 10, Axis.X), 10, 8) == pytest.approx(8 * math.tan(math.radians(10)))

    def test_ridge_defaults_to_longer_side(self) -> None:
        assert ridge_axis(self.roof(RoofType.GABLE, 35), 6, 12) is Axis.Y
        assert roof_span(self.roof(RoofType.GABLE, 35), 6, 12) == 6

    def test_hip_ridge_length(self) -> None:
        assert hip_ridge_length(self.roof(RoofType.HIP, 25, Axis.X), 16, 10) == pytest.approx(6)
        assert hip_ridge_length(self.roof(RoofType.HIP, 25, Axis.Y), 16, 10) < 0
