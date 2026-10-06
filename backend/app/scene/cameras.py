"""Camera placement calculated from the building's geometry.

The projection here follows Blender's camera model (sensor width 36 mm fitted to the wider
image dimension, up along world +Z), so a camera that frames the building in these
calculations frames it in Blender too. tests/blender checks that with Blender's own
world_to_camera_view.
"""

import math
from dataclasses import dataclass

from app.geometry.rect import Rect
from app.models.building import BuildingSpecification
from app.models.room import Room, RoomType
from app.scene.model import Box3, SceneCamera

SENSOR = 36.0
EXTERIOR_LENS = 35.0
INTERIOR_LENS = 16.0
FILL = 0.88            # the building fills at most 88% of the frame's half-width or half-height
EYE_HEIGHT = 1.55
CORNER_INSET = 0.35    # interior cameras stand this far from the walls
PLAN_MARGIN = 1.12

EXTERIOR_VIEWS = {
    "Front": (-0.45, -1.0, 0.16),
    "Rear": (0.45, 1.0, 0.16),
    "Aerial": (-0.75, -1.0, 1.05),
}


@dataclass(frozen=True)
class View:
    location: tuple[float, float, float]
    target: tuple[float, float, float]
    lens: float
    aspect: float


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    length = math.sqrt(_dot(a, a))
    return tuple(x / length for x in a)


def project(point, view: View) -> tuple[float, float, float]:
    """(x, y, depth) with x and y in [-1, 1] across the visible frame; depth > 0 in front."""
    forward = _norm(_sub(view.target, view.location))
    right = _norm(_cross(forward, (0.0, 0.0, 1.0)))
    up = _cross(right, forward)
    v = _sub(point, view.location)
    depth = _dot(v, forward)
    half_wide = (SENSOR / 2) / view.lens
    half_x, half_y = (half_wide, half_wide / view.aspect) if view.aspect >= 1 else (half_wide * view.aspect, half_wide)
    return _dot(v, right) / (depth * half_x), _dot(v, up) / (depth * half_y), depth


def corners(box: Box3) -> list[tuple[float, float, float]]:
    return [(x, y, z) for x in (box.min[0], box.max[0]) for y in (box.min[1], box.max[1]) for z in (box.min[2], box.max[2])]


def frames(box: Box3, view: View, fill: float = 1.0) -> bool:
    for p in corners(box):
        x, y, depth = project(p, view)
        if depth <= 0 or abs(x) > fill or abs(y) > fill:
            return False
    return True


def fit_exterior(box: Box3, direction, aspect: float, lens: float = EXTERIOR_LENS, min_height: float = 1.6) -> View:
    """The closest camera along `direction` from the building's centre that frames the whole box."""
    centre = tuple((a + b) / 2 for a, b in zip(box.min, box.max))
    d = _norm(direction)
    radius = math.dist(box.min, box.max) / 2

    def view_at(distance: float) -> View:
        loc = [c + distance * k for c, k in zip(centre, d)]
        loc[2] = max(loc[2], box.min[2] + min_height)
        return View(tuple(round(v, 3) for v in loc), tuple(round(v, 3) for v in centre), lens, aspect)  # type: ignore[arg-type]

    lo, hi = radius * 0.5, radius * 40
    if not frames(box, view_at(hi), FILL):
        raise ValueError("cannot frame the building")  # unreachable in practice: far enough always fits
    for _ in range(40):  # bisection on distance: nearer frames are tighter
        mid = (lo + hi) / 2
        if frames(box, view_at(mid), FILL):
            hi = mid
        else:
            lo = mid
    return view_at(hi)


def exterior_cameras(box: Box3, aspect: float) -> list[SceneCamera]:
    cameras = []
    for label, direction in EXTERIOR_VIEWS.items():
        view = fit_exterior(box, direction, aspect)
        cameras.append(SceneCamera(name=f"Camera_Exterior_{label}", projection="perspective", location=view.location,
                                   target=view.target, lens=view.lens, tags={"role": f"exterior_{label.lower()}"}))
    return cameras


# ----------------------------------------------------------------------------- interiors

INTERIOR_ROLES = {
    "LivingRoom": (RoomType.LIVING_ROOM, RoomType.OPEN_PLAN_LIVING, RoomType.KITCHEN_DINING),
    "Kitchen": (RoomType.KITCHEN, RoomType.KITCHEN_DINING, RoomType.OPEN_PLAN_LIVING),
}


def _master_bedroom(spec: BuildingSpecification) -> Room | None:
    bedrooms = [r for r in spec.rooms if r.type is RoomType.BEDROOM]
    named = [r for r in bedrooms if "master" in r.name.lower() or "main" in r.name.lower()]
    pool = named or bedrooms
    return max(pool, key=lambda r: r.area, default=None)


def _inner(room: Room, spec: BuildingSpecification) -> Rect:
    b = spec.building
    inset = CORNER_INSET + b.wall_thickness / 2
    return Rect(room.x + inset, room.y + inset, room.width - 2 * inset, room.depth - 2 * inset)


def _window_side_weights(room: Room, spec: BuildingSpecification) -> dict[str, float]:
    weights: dict[str, float] = {}
    for w in spec.windows:
        if w.room == room.id:
            weights[w.wall.value] = weights.get(w.wall.value, 0.0) + w.width
    for d in spec.doors:
        if d.connects_room_a == room.id and d.is_external and d.type.value == "patio_sliding":
            side = {0: "front", 180: "rear", 90: "left", 270: "right"}[d.rotation]
            weights[side] = weights.get(side, 0.0) + d.width
    return weights


def interior_camera(name: str, room: Room, spec: BuildingSpecification, aspect: float, avoid_corner: int | None = None) -> tuple[SceneCamera, int] | None:
    """A camera in the corner opposite the room's main windows, looking across the room."""
    inner = _inner(room, spec)
    if inner.width < 0.5 or inner.depth < 0.5:
        return None
    floor = spec.floor(room.floor)
    e = floor.elevation if floor else 0.0
    ceiling = e + (room.height or (floor.height - spec.building.slab_thickness if floor else 2.4))
    eye = min(e + EYE_HEIGHT, ceiling - 0.25)
    corner_points = [(inner.x, inner.y), (inner.x2, inner.y), (inner.x2, inner.y2), (inner.x, inner.y2)]
    weights = _window_side_weights(room, spec)

    def facing_score(index: int) -> float:
        cx, cy = corner_points[index]
        tx, ty = corner_points[(index + 2) % 4]
        score = 0.0
        score += weights.get("rear", 0) if ty > cy else weights.get("front", 0)
        score += weights.get("right", 0) if tx > cx else weights.get("left", 0)
        return score

    order = sorted(range(4), key=lambda i: (-facing_score(i), i))
    index = next(i for i in order if i != avoid_corner)
    cx, cy = corner_points[index]
    tx, ty = corner_points[(index + 2) % 4]
    camera = SceneCamera(name=name, projection="perspective", location=(round(cx, 3), round(cy, 3), round(eye, 3)),
                         target=(round(tx, 3), round(ty, 3), round(e + 1.0, 3)), lens=INTERIOR_LENS,
                         tags={"role": f"interior_{name.split('_')[-1].lower()}", "room_id": room.id, "floor": str(room.floor)})
    return camera, index


def interior_cameras(spec: BuildingSpecification, aspect: float) -> list[SceneCamera]:
    cameras: list[SceneCamera] = []
    used: dict[str, int] = {}
    for label, types in INTERIOR_ROLES.items():
        room = next((r for t in types for r in spec.rooms if r.type is t), None)
        if room is None:
            continue
        made = interior_camera(f"Camera_Interior_{label}", room, spec, aspect, avoid_corner=used.get(room.id))
        if made:
            cameras.append(made[0])
            used[room.id] = made[1]
    master = _master_bedroom(spec)
    if master is not None:
        made = interior_camera("Camera_Interior_MasterBedroom", master, spec, aspect)
        if made:
            cameras.append(made[0])
    return cameras


# ----------------------------------------------------------------------------- floor plans

def floor_plan_camera(name: str, level: int, spec: BuildingSpecification, aspect: float, outer: Rect) -> SceneCamera:
    floor = spec.floor(level)
    e = floor.elevation if floor else 0.0
    cx, cy = outer.x + outer.width / 2, outer.y + outer.depth / 2
    # Orthographic scale is the visible width; fit the plan's width, or its depth scaled by the aspect.
    scale = max(outer.width, outer.depth * aspect) * PLAN_MARGIN
    return SceneCamera(name=name, projection="orthographic", location=(round(cx, 3), round(cy, 3), round(e + 30.0, 3)),
                       target=(round(cx, 3), round(cy, 3), round(e, 3)), ortho_scale=round(scale, 3), clip_end=60.0,
                       tags={"role": "floor_plan", "floor": str(level)})
