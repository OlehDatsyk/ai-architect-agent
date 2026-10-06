"""Sky, sun and interior lighting.

Two presets are built into every scene:
    Day      World_Day + Sun_Day, from the specification's sun direction and sky type
    Evening  World_Evening + Sun_Evening: a low warm sun and a dusk sky
Interior ceiling lights are on in both. The evening sun's collection is excluded from
rendering until it is switched on (see docs/blender-integration.md).

Sun direction: azimuth is measured clockwise from +Y (taken as north, so the building's
front faces south) and elevation upwards from the horizon.
"""

import math

from app.geometry.rect import Rect
from app.models.building import BuildingSpecification
from app.models.room import RoomType
from app.scene.model import SceneLight, SceneWorld

EVENING_AZIMUTH = 250.0
EVENING_ELEVATION = 7.0
WARM_WHITE = (1.0, 0.82, 0.62)      # roughly 3000 K
WATTS_PER_M2 = 14.0
LIGHT_SPACING = 4.5                 # one ceiling light per 4.5 m along the room's long side
NO_CEILING_LIGHT = frozenset({RoomType.GARAGE})

SKIES = {
    #            horizon               zenith               ground              strength  sun W/m²  sun angle
    "clear":    ((0.70, 0.80, 0.92), (0.18, 0.36, 0.75), (0.25, 0.24, 0.22), 1.0, 4.0, 0.5),
    "overcast": ((0.70, 0.72, 0.75), (0.48, 0.52, 0.58), (0.22, 0.22, 0.22), 1.3, 1.2, 15.0),
    "sunset":   ((0.95, 0.62, 0.38), (0.25, 0.32, 0.55), (0.18, 0.15, 0.13), 0.8, 3.0, 1.0),
}


def sun_direction(azimuth_deg: float, elevation_deg: float) -> tuple[float, float, float]:
    """Unit vector pointing from the scene towards the sun."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    return (math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el))


def _sun(name: str, collection: str, azimuth: float, elevation: float, energy: float, colour, angle: float, preset: str) -> SceneLight:
    d = sun_direction(azimuth, elevation)
    location = tuple(round(50 * c, 3) for c in d)
    return SceneLight(name=name, collection=collection, kind="sun", location=location, target=(0.0, 0.0, 0.0),
                      energy=energy, colour=colour, size=angle,
                      tags={"preset": preset, "azimuth": f"{azimuth:g}", "elevation": f"{elevation:g}"})


def presets(spec: BuildingSpecification) -> tuple[list[SceneWorld], list[SceneLight]]:
    env = spec.environment
    horizon, zenith, ground, strength, sun_energy, angle = SKIES[env.sky]
    worlds = [
        SceneWorld(name="World_Day", horizon=horizon, zenith=zenith, ground=ground, strength=strength),
        SceneWorld(name="World_Evening", horizon=(0.85, 0.45, 0.22), zenith=(0.05, 0.08, 0.2), ground=(0.06, 0.05, 0.05), strength=0.35),
    ]
    suns = [
        _sun("Sun_Day", "LIGHTS_DAY", env.sun.azimuth_deg, max(env.sun.elevation_deg, 1.0), sun_energy, (1.0, 0.97, 0.92), angle, "day"),
        _sun("Sun_Evening", "LIGHTS_EVENING", EVENING_AZIMUTH, EVENING_ELEVATION, 2.0, (1.0, 0.55, 0.3), 1.5, "evening"),
    ]
    return worlds, suns


def ceiling_lights(spec: BuildingSpecification, names) -> list[SceneLight]:
    """Area lights just below each room's ceiling, in a row along its longer side."""
    b = spec.building
    lights = []
    for room in spec.rooms:
        if room.type in NO_CEILING_LIGHT:
            continue
        floor = spec.floor(room.floor)
        if floor is None:
            continue
        ceiling = floor.elevation + (room.height or floor.height - b.slab_thickness)
        inner = Rect(room.x + b.wall_thickness / 2, room.y + b.wall_thickness / 2,
                     room.width - b.wall_thickness, room.depth - b.wall_thickness)
        if inner.width <= 0.2 or inner.depth <= 0.2:
            continue
        along_x = inner.width >= inner.depth
        long_side = inner.width if along_x else inner.depth
        count = max(1, math.ceil(long_side / LIGHT_SPACING))
        size = round(min(max(min(inner.width, inner.depth) * 0.3, 0.3), 1.2), 3)
        energy = round(min(max(room.area * WATTS_PER_M2 / count, 30.0), 800.0), 1)
        z = round(ceiling - 0.05, 3)
        for i in range(count):
            t = (i + 0.5) / count
            x = inner.x + (inner.width * t if along_x else inner.width / 2)
            y = inner.y + (inner.depth / 2 if along_x else inner.depth * t)
            lights.append(SceneLight(
                name=names(f"Light_{room.name}"), collection="LIGHTS_INTERIOR", kind="area",
                location=(round(x, 3), round(y, 3), z), target=(round(x, 3), round(y, 3), round(z - 1, 3)),
                energy=energy, colour=WARM_WHITE, size=size, tags={"room_id": room.id, "floor": str(room.floor)},
            ))
    return lights
