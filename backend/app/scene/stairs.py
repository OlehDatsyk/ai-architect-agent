"""Stairs as stepped solids, and the stairwell holes they need in the floor above."""

from app.geometry.rect import Rect
from app.geometry.stairs import stair_footprint
from app.models.stairs import Stair, StairDirection
from app.scene.model import Box3


def stair_steps(stair: Stair, floor_level_z: float, finish: float) -> list[Box3]:
    """One box per tread, each rising from the floor finish to that tread's top.
    The last riser steps onto the floor above, so a flight of n risers has n - 1 treads."""
    r = stair_footprint(stair)
    boxes = []
    for i in range(1, stair.risers):
        top = floor_level_z + i * stair.rise
        lo, hi = (i - 1) * stair.run, i * stair.run
        if stair.direction is StairDirection.FRONT_TO_REAR:
            x0, x1, y0, y1 = r.x, r.x2, r.y + lo, r.y + hi
        elif stair.direction is StairDirection.REAR_TO_FRONT:
            x0, x1, y0, y1 = r.x, r.x2, r.y2 - hi, r.y2 - lo
        elif stair.direction is StairDirection.LEFT_TO_RIGHT:
            x0, x1, y0, y1 = r.x + lo, r.x + hi, r.y, r.y2
        else:
            x0, x1, y0, y1 = r.x2 - hi, r.x2 - lo, r.y, r.y2
        boxes.append(Box3(min=(round(x0, 4), round(y0, 4), round(floor_level_z + finish, 4)),
                          max=(round(x1, 4), round(y1, 4), round(top, 4))))
    return boxes


def stairwell(stair: Stair) -> Rect:
    """The opening needed in the slab above (and in the landing floor) for headroom."""
    return stair_footprint(stair)
