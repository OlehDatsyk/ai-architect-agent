"""Stair calculations.

The limits below are typical comfort values used to flag unusual stairs. They are not a
building-regulations compliance check.
"""

import math
from dataclasses import dataclass

from app.geometry.rect import Rect
from app.models.stairs import Stair, StairDirection

MIN_RISE = 0.15
TARGET_RISE = 0.19
MAX_RISE = 0.22
MIN_RUN = 0.22
DEFAULT_RUN = 0.25
MAX_PITCH_DEG = 42.0
MIN_WIDTH = 0.8


@dataclass(frozen=True)
class StairDimensions:
    risers: int
    rise: float
    run: float

    @property
    def treads(self) -> int:
        return self.risers - 1

    @property
    def going_length(self) -> float:
        return self.run * self.treads

    @property
    def pitch_deg(self) -> float:
        return pitch_deg(self.rise, self.run)


def pitch_deg(rise: float, run: float) -> float:
    return math.degrees(math.atan2(rise, run))


def calculate_stair(floor_to_floor: float, run: float = DEFAULT_RUN, target_rise: float = TARGET_RISE) -> StairDimensions:
    """Choose a riser count close to the target rise without exceeding MAX_RISE."""
    if floor_to_floor <= 0:
        raise ValueError("floor_to_floor must be positive")
    risers = max(2, round(floor_to_floor / target_rise), math.ceil(floor_to_floor / MAX_RISE - 1e-9))
    return StairDimensions(risers=risers, rise=floor_to_floor / risers, run=run)


def going_length(stair: Stair) -> float:
    return stair.run * (stair.risers - 1)


def stair_footprint(stair: Stair) -> Rect:
    length = going_length(stair)
    if stair.direction in (StairDirection.FRONT_TO_REAR, StairDirection.REAR_TO_FRONT):
        return Rect(stair.x, stair.y, stair.width, length)
    return Rect(stair.x, stair.y, length, stair.width)


def stair_start_point(stair: Stair, inset: float = 0.05) -> tuple[float, float]:
    """A point on the first tread, used to find the room the stair starts in."""
    r = stair_footprint(stair)
    cx, cy = r.x + r.width / 2, r.y + r.depth / 2
    return {
        StairDirection.FRONT_TO_REAR: (cx, r.y + inset),
        StairDirection.REAR_TO_FRONT: (cx, r.y2 - inset),
        StairDirection.LEFT_TO_RIGHT: (r.x + inset, cy),
        StairDirection.RIGHT_TO_LEFT: (r.x2 - inset, cy),
    }[stair.direction]


def stair_arrival_point(stair: Stair, step_off: float = 0.1) -> tuple[float, float]:
    """A point just beyond the top of the flight, on the upper floor."""
    r = stair_footprint(stair)
    cx, cy = r.x + r.width / 2, r.y + r.depth / 2
    return {
        StairDirection.FRONT_TO_REAR: (cx, r.y2 + step_off),
        StairDirection.REAR_TO_FRONT: (cx, r.y - step_off),
        StairDirection.LEFT_TO_RIGHT: (r.x2 + step_off, cy),
        StairDirection.RIGHT_TO_LEFT: (r.x - step_off, cy),
    }[stair.direction]
