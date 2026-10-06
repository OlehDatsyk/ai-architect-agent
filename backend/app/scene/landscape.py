"""Site surfaces and planting around the building.

Plant proportions are fixed fractions of the specified height so the validator, which warns
about planting that would touch the building, and the geometry agree on plant sizes.
"""

import math
import random
from dataclasses import dataclass

from app.geometry.rect import Rect
from app.models.environment import SiteArea, Vegetation, VegetationKind
from app.scene.model import Box3, MeshData
from app.scene.shapes import rect_box, subtract

SITE_THICKNESS = 0.05
CLEARANCE = 0.3          # planting keeps this far from the building
MIN_RADIUS = 0.4         # smaller than this and a plant is left out
HEDGE_LENGTH, HEDGE_WIDTH = 2.5, 0.7

# Fractions of a plant's height.
TREE_CANOPY_RADIUS = 0.32
TREE_CANOPY_CENTRE = 0.62
TREE_CANOPY_HEIGHT = 0.38   # vertical radius
SHRUB_RADIUS = 0.6
JITTER = 0.12            # canopies bulge up to this fraction beyond their nominal radius


def plant_radius(plant: Vegetation) -> float:
    """Furthest horizontal reach of a plant from its position, including the irregularity of
    its canopy (half the length for hedges)."""
    if plant.kind is VegetationKind.TREE:
        return TREE_CANOPY_RADIUS * plant.size * (1 + JITTER)
    if plant.kind is VegetationKind.SHRUB:
        return SHRUB_RADIUS * plant.size * (1 + JITTER)
    return math.hypot(HEDGE_LENGTH / 2, HEDGE_WIDTH / 2)


def distance_to_rect(x: float, y: float, r: Rect) -> float:
    dx = max(r.x - x, 0.0, x - r.x2)
    dy = max(r.y - y, 0.0, y - r.y2)
    return math.hypot(dx, dy)


def site_surfaces(areas: list[SiteArea], building: Rect, ground: Rect, z_ground: float) -> list[tuple[SiteArea, list[Box3]]]:
    """Each area as thin slabs on the ground, clipped to stay off the building and inside the
    ground, and never under an earlier area (driveway, then patio, then paths)."""
    taken: list[Rect] = [building]
    result = []
    for area in areas:
        rect = Rect(area.x, area.y, area.width, area.depth)
        clipped = Rect(max(rect.x, ground.x), max(rect.y, ground.y), 0, 0)
        clipped = Rect(clipped.x, clipped.y, min(rect.x2, ground.x2) - clipped.x, min(rect.y2, ground.y2) - clipped.y)
        if clipped.width <= 0 or clipped.depth <= 0:
            continue
        pieces = [p for p in subtract(clipped, taken) if p.width > 0.05 and p.depth > 0.05]
        if pieces:
            result.append((area, [rect_box(p, z_ground, z_ground + SITE_THICKNESS) for p in pieces]))
            taken.append(clipped)
    return result


@dataclass(frozen=True)
class PlantGeometry:
    plant: Vegetation
    foliage: MeshData | Box3
    trunk: MeshData | None
    scale: float  # 1.0, or less if the plant was shrunk to keep clear of the building


def plant_geometry(plant: Vegetation, building: Rect, z_ground: float) -> PlantGeometry | None:
    """None if the plant cannot fit beside the building even when shrunk."""
    reach = plant_radius(plant)
    room = distance_to_rect(plant.x, plant.y, building) - CLEARANCE
    scale = 1.0 if room >= reach else room / reach
    if scale < 1.0 and reach * scale < MIN_RADIUS:
        return None  # it would have to shrink to almost nothing to fit
    rng = random.Random(plant.id)  # deterministic: the same plant always gets the same shape
    size = plant.size * scale

    if plant.kind is VegetationKind.HEDGE:
        half = HEDGE_LENGTH / 2 * scale
        box = Box3(min=(round(plant.x - half, 4), round(plant.y - HEDGE_WIDTH / 2, 4), round(z_ground, 4)),
                   max=(round(plant.x + half, 4), round(plant.y + HEDGE_WIDTH / 2, 4), round(z_ground + plant.size, 4)))
        return PlantGeometry(plant, box, None, scale)

    if plant.kind is VegetationKind.SHRUB:
        r = SHRUB_RADIUS * size
        mound = blob(plant.x, plant.y, z_ground + 0.4 * size, r, 0.45 * size, rng, rings=4, segments=8, bottom=z_ground)
        return PlantGeometry(plant, mound, None, scale)

    canopy_z = z_ground + TREE_CANOPY_CENTRE * size
    vertical = TREE_CANOPY_HEIGHT * size
    canopy = blob(plant.x, plant.y, canopy_z, TREE_CANOPY_RADIUS * size, vertical, rng, rings=5, segments=10)
    trunk = cylinder(plant.x, plant.y, z_ground, canopy_z - vertical, 0.06 + 0.012 * size, sides=8)
    return PlantGeometry(plant, canopy, trunk, scale)


def blob(cx: float, cy: float, cz: float, radius: float, vertical: float, rng: random.Random,
         rings: int, segments: int, bottom: float | None = None) -> MeshData:
    """A closed, slightly irregular ellipsoid: a pole at the top and bottom with rings between.
    With `bottom`, vertices are kept at or above that height (a mound sitting on the ground)."""
    vertices = [(cx, cy, cz + vertical)]
    for i in range(1, rings + 1):
        polar = math.pi * i / (rings + 1)
        for j in range(segments):
            azimuth = 2 * math.pi * j / segments + (i % 2) * math.pi / segments
            wobble = 1 + rng.uniform(-JITTER, JITTER)
            x = cx + radius * wobble * math.sin(polar) * math.cos(azimuth)
            y = cy + radius * wobble * math.sin(polar) * math.sin(azimuth)
            z = cz + vertical * math.cos(polar) * (1 + rng.uniform(-0.08, 0.08))
            vertices.append((x, y, z if bottom is None else max(z, bottom + 0.01)))
    vertices.append((cx, cy, cz - vertical if bottom is None else bottom))
    last = len(vertices) - 1
    faces: list[list[int]] = []
    for j in range(segments):  # top cap
        faces.append([0, 1 + j, 1 + (j + 1) % segments])
    for i in range(rings - 1):  # bands
        a, b = 1 + i * segments, 1 + (i + 1) * segments
        for j in range(segments):
            k = (j + 1) % segments
            faces.append([a + j, b + j, b + k, a + k])
    base = 1 + (rings - 1) * segments
    for j in range(segments):  # bottom cap
        faces.append([base + j, last, base + (j + 1) % segments])
    return MeshData(vertices=[tuple(round(c, 4) for c in v) for v in vertices], faces=faces)  # type: ignore[misc]


def cylinder(cx: float, cy: float, z0: float, z1: float, radius: float, sides: int) -> MeshData:
    ring = [(cx + radius * math.cos(2 * math.pi * k / sides), cy + radius * math.sin(2 * math.pi * k / sides)) for k in range(sides)]
    vertices = [(x, y, z0) for x, y in ring] + [(x, y, z1) for x, y in ring]
    faces = [list(reversed(range(sides))), [sides + k for k in range(sides)]]
    faces += [[k, (k + 1) % sides, sides + (k + 1) % sides, sides + k] for k in range(sides)]
    return MeshData(vertices=[tuple(round(c, 4) for c in v) for v in vertices], faces=faces)  # type: ignore[misc]
