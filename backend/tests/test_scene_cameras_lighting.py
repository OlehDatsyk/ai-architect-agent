"""Cameras, lighting presets, view layers and inner wall faces in the compiled scene."""

import math

import pytest

from app.geometry.rect import Rect
from app.models import BuildingSpecification
from app.scene.cameras import FILL, View, corners, frames, project
from app.scene.compiler import compile_scene
from app.scene.lighting import sun_direction
from app.scene.model import union
from tests.helpers import example
from tests.scene_cases import all_specs


def scene_of(slug: str):
    """The specification as the build endpoint sees it: validated, so room heights are filled in."""
    from app.validation import validate_specification

    spec = validate_specification(BuildingSpecification.model_validate(example(slug))).specification
    return spec, compile_scene(spec)


def building_bounds(scene):
    return union([b for e in scene.elements if e.kind not in ("ground", "site", "vegetation")
                  for b in ([e.mesh.bounds()] if e.mesh else e.boxes)])


@pytest.mark.parametrize("case", sorted(all_specs()))
def test_exterior_cameras_frame_the_whole_building_snugly(case: str) -> None:
    scene = compile_scene(all_specs()[case])
    box = building_bounds(scene)
    exterior = [c for c in scene.cameras if c.tags["role"].startswith("exterior")]
    assert [c.name for c in exterior] == ["Camera_Exterior_Front", "Camera_Exterior_Rear", "Camera_Exterior_Aerial"]
    for cam in exterior:
        view = View(cam.location, cam.target, cam.lens, scene.render.aspect)
        assert frames(box, view, FILL + 1e-6), f"{cam.name} crops the building"
        reach = max(max(abs(x), abs(y)) for x, y, _ in (project(p, view) for p in corners(box)))
        assert reach > 0.6, f"{cam.name} is so far away the building looks small ({reach:.2f})"
        assert cam.location[2] >= box.min[2] + 1.5


def test_front_and_rear_cameras_are_on_the_right_sides() -> None:
    spec, scene = scene_of("british-family-house")
    by = {c.name: c for c in scene.cameras}
    assert by["Camera_Exterior_Front"].location[1] < 0 < spec.building.depth < by["Camera_Exterior_Rear"].location[1]
    assert by["Camera_Exterior_Aerial"].location[2] > by["Camera_Exterior_Front"].location[2]


@pytest.mark.parametrize("slug", ["british-family-house", "modern-bungalow", "luxury-house", "scandinavian-house"])
def test_interior_cameras_stand_in_their_room_and_look_across_it(slug: str) -> None:
    spec, scene = scene_of(slug)
    rooms = {r.id: r for r in spec.rooms}
    interior = [c for c in scene.cameras if c.tags["role"].startswith("interior")]
    assert {c.name for c in interior} == {"Camera_Interior_LivingRoom", "Camera_Interior_Kitchen", "Camera_Interior_MasterBedroom"}
    for cam in interior:
        room = rooms[cam.tags["room_id"]]
        rect = Rect(room.x, room.y, room.width, room.depth)
        floor = spec.floor(room.floor)
        assert rect.contains_point(cam.location[0], cam.location[1], tol=-0.3)  # well inside the walls
        assert rect.contains_point(cam.target[0], cam.target[1], tol=-0.3)
        assert floor.elevation + 1.2 < cam.location[2] < floor.elevation + room.height
        assert math.dist(cam.location[:2], cam.target[:2]) > 1.5


def test_open_plan_room_gets_two_different_viewpoints() -> None:
    _, scene = scene_of("modern-bungalow")
    by = {c.name: c for c in scene.cameras}
    living, kitchen = by["Camera_Interior_LivingRoom"], by["Camera_Interior_Kitchen"]
    assert living.tags["room_id"] == kitchen.tags["room_id"] and living.location != kitchen.location


def test_camera_roles_without_a_matching_room_are_skipped() -> None:
    _, scene = scene_of("small-office")
    names = {c.name for c in scene.cameras}
    assert "Camera_Interior_Kitchen" in names
    assert not names & {"Camera_Interior_LivingRoom", "Camera_Interior_MasterBedroom"}


@pytest.mark.parametrize("slug", ["british-family-house", "modern-bungalow"])
def test_one_plan_camera_and_view_layer_per_floor(slug: str) -> None:
    spec, scene = scene_of(slug)
    box = building_bounds(scene)
    plans = [c for c in scene.cameras if c.tags["role"] == "floor_plan"]
    assert len(plans) == len(spec.floors) == len(scene.view_layers)
    for cam, layer, floor in zip(plans, scene.view_layers, spec.floors):
        assert cam.projection == "orthographic"
        assert cam.location[:2] == cam.target[:2] and cam.location[2] > cam.target[2]  # straight down
        assert cam.ortho_scale >= box.max[0] - box.min[0] and cam.ortho_scale >= (box.max[1] - box.min[1]) * scene.render.aspect
        upper = {f"FLOOR_{f.level}" for f in spec.floors if f.level > floor.level}
        assert set(layer.exclude) == {"ROOF", f"CEILING_{floor.level}"} | upper


def test_day_and_evening_presets() -> None:
    spec, scene = scene_of("british-family-house")
    suns = {light.name: light for light in scene.lights if light.kind == "sun"}
    day, evening = suns["Sun_Day"], suns["Sun_Evening"]
    expected = sun_direction(spec.environment.sun.azimuth_deg, spec.environment.sun.elevation_deg)
    actual = [(a - b) for a, b in zip(day.location, day.target)]
    length = math.sqrt(sum(c * c for c in actual))
    assert [c / length for c in actual] == pytest.approx(list(expected), abs=1e-3)
    assert evening.location[2] < day.location[2]  # a low evening sun
    assert {w.name for w in scene.worlds} == {"World_Day", "World_Evening"}
    assert scene.render.active_world == "World_Day" and scene.render.hidden_collections == ["LIGHTS_EVENING"]
    assert scene.render.active_camera == "Camera_Exterior_Front"


def test_sky_type_changes_the_day_world() -> None:
    _, overcast = scene_of("scandinavian-house")  # sky: overcast
    _, clear = scene_of("british-family-house")
    o = next(w for w in overcast.worlds if w.name == "World_Day")
    c = next(w for w in clear.worlds if w.name == "World_Day")
    assert o.zenith != c.zenith
    assert next(light for light in overcast.lights if light.name == "Sun_Day").energy < next(light for light in clear.lights if light.name == "Sun_Day").energy


def test_sun_direction_convention() -> None:
    assert sun_direction(0, 0) == pytest.approx((0, 1, 0))      # north = +Y (behind the house)
    assert sun_direction(90, 0) == pytest.approx((1, 0, 0))     # east = +X
    assert sun_direction(180, 90) == pytest.approx((0, 0, 1), abs=1e-9)


@pytest.mark.parametrize("slug", ["british-family-house", "small-office"])
def test_ceiling_lights_sit_inside_rooms_just_below_the_ceiling(slug: str) -> None:
    spec, scene = scene_of(slug)
    rooms = {r.id: r for r in spec.rooms}
    lights = [light for light in scene.lights if light.kind == "area"]
    lit = {light.tags["room_id"] for light in lights}
    assert lit == {r.id for r in spec.rooms if r.type.value != "garage"}
    for light in lights:
        room = rooms[light.tags["room_id"]]
        floor = spec.floor(room.floor)
        assert Rect(room.x, room.y, room.width, room.depth).contains_point(light.location[0], light.location[1], tol=-0.1)
        assert floor.elevation + room.height - 0.1 < light.location[2] < floor.elevation + room.height
        assert light.target[2] < light.location[2]  # facing down
    assert len({light.name for light in scene.lights}) == len(scene.lights)


def test_exterior_walls_are_plastered_on_the_inside() -> None:
    spec, scene = scene_of("british-family-house")
    centre = (spec.building.width / 2, spec.building.depth / 2)
    for wall in (e for e in scene.elements if e.tags.get("wall_type") == "exterior"):
        assert wall.inner_material == "MAT_PaintedPlaster" and wall.material.startswith("MAT_Brick")
        b = wall.bounds
        mid = ((b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2)
        axis = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}[wall.inward]
        assert (centre[0] - mid[0]) * axis[0] + (centre[1] - mid[1]) * axis[1] > 0, f"{wall.name} plaster faces outwards"
    assert all(e.inner_material is None for e in scene.elements if e.tags.get("wall_type") == "interior")


def test_floor_plan_cameras_name_their_view_layer() -> None:
    from app.models import BuildingSpecification
    from app.scene.compiler import compile_scene
    from tests.helpers import example

    scene = compile_scene(BuildingSpecification.model_validate(example()))
    layers = {v.name: v for v in scene.view_layers}
    plans = [c for c in scene.cameras if c.tags.get("role") == "floor_plan"]
    assert len(plans) == 2
    for camera in plans:
        layer = layers[camera.tags["view_layer"]]
        assert "ROOF" in layer.exclude
