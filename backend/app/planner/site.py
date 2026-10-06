"""Driveway, front path, patio and a little planting around the footprint."""

from app.geometry.rect import Rect
from app.models.environment import Environment, SiteArea, Vegetation, VegetationKind
from app.models.materials import MaterialId, MaterialRef
from app.models.opening import Door
from app.planner.model import Box

DRIVEWAY_LENGTH = 6.0
PATIO_DEPTH = 3.5


def plan_site(width: float, depth: float, front_door: Door | None, garage: Box | None,
              patio_room: Box | None, want_driveway: bool, want_patio: bool) -> Environment:
    driveway = None
    if want_driveway:
        if garage is not None and garage.rect is not None and garage.rect.y == 0:
            x, w = garage.rect.x, garage.rect.width
        else:
            x, w = 0.0, min(3.2, width / 3)
        driveway = SiteArea(id="driveway", x=x, y=-DRIVEWAY_LENGTH, width=w, depth=DRIVEWAY_LENGTH,
                            material=MaterialRef(id=MaterialId.PAVING))

    paths = []
    if front_door is not None and front_door.rotation == 0:
        path = Rect(round(front_door.position.x - 0.6, 2), -DRIVEWAY_LENGTH, 1.2, DRIVEWAY_LENGTH)
        clashes = driveway is not None and path.intersection_area(Rect(driveway.x, driveway.y, driveway.width, driveway.depth)) > 0
        if not clashes:
            paths.append(SiteArea(id="front_path", x=path.x, y=path.y, width=path.width, depth=path.depth,
                                  material=MaterialRef(id=MaterialId.PAVING)))

    patio = None
    if want_patio:
        if patio_room is not None and patio_room.rect is not None:
            x, w = patio_room.rect.x, patio_room.rect.width
        else:
            x, w = 0.0, width
        patio = SiteArea(id="patio", x=x, y=depth, width=w, depth=PATIO_DEPTH, material=MaterialRef(id=MaterialId.PAVING))

    vegetation = [
        Vegetation(id="tree_front", kind=VegetationKind.TREE, x=round(width + 3.0, 2), y=-3.0, size=6),
        Vegetation(id="tree_rear", kind=VegetationKind.TREE, x=-3.0, y=round(depth + 4.0, 2), size=7),
    ]
    return Environment(driveway=driveway, patio=patio, paths=paths, vegetation=vegetation)
