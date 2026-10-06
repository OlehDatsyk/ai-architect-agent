"""Site surfaces and planting."""

import math

import pytest

from app.geometry.rect import Rect
from app.models import BuildingSpecification, MaterialRef, SiteArea, Vegetation
from app.scene.compiler import compile_scene
from app.scene.landscape import CLEARANCE, plant_geometry, plant_radius, site_surfaces
from app.validation import validate_specification
from tests.helpers import example, find
from tests.scene_cases import all_specs
from tests.test_scene_architecture import closed_and_outward

BUILDING = Rect(-0.15, -0.15, 10.3, 8.3)
GROUND = Rect(-20, -20, 50, 48)
Z = -0.15


def area(aid: str, x, y, w, d) -> SiteArea:
    return SiteArea(id=aid, x=x, y=y, width=w, depth=d, material=MaterialRef(id="paving"))


def test_site_areas_sit_on_the_ground_and_stay_off_the_plinth() -> None:
    [(_, boxes)] = site_surfaces([area("drive", 0, -6, 3, 6)], BUILDING, GROUND, Z)
    assert all(b.min[2] == Z and b.max[2] == pytest.approx(Z + 0.05) for b in boxes)
    assert max(b.max[1] for b in boxes) == pytest.approx(-0.15)  # stops at the wall's outer face


def test_earlier_areas_win_where_areas_overlap() -> None:
    result = site_surfaces([area("drive", 0, -6, 3, 6), area("path", 2, -6, 2, 6)], BUILDING, GROUND, Z)
    path_boxes = {a.id: b for a, b in result}["path"]
    assert min(b.min[0] for b in path_boxes) == pytest.approx(3)


def test_areas_outside_the_ground_are_dropped() -> None:
    assert site_surfaces([area("far", 100, 100, 3, 3)], BUILDING, GROUND, Z) == []


@pytest.mark.parametrize("kind", ["tree", "shrub"])
@pytest.mark.parametrize("size", [0.8, 2.0, 6.0, 15.0])
def test_plants_are_closed_outward_meshes(kind: str, size: float) -> None:
    for n in range(5):
        g = plant_geometry(Vegetation(id=f"p_{n}", kind=kind, x=40, y=-15, size=size), BUILDING, Z)
        assert g is not None
        for mesh in (g.foliage, g.trunk):
            if mesh is not None:
                closed, volume = closed_and_outward(mesh)
                assert closed and volume > 0


def test_tree_trunk_meets_the_canopy_and_the_ground() -> None:
    g = plant_geometry(Vegetation(id="oak", kind="tree", x=30, y=-10, size=8), BUILDING, Z)
    trunk_top = max(v[2] for v in g.trunk.vertices)
    canopy_bottom = min(v[2] for v in g.foliage.vertices)
    assert min(v[2] for v in g.trunk.vertices) == pytest.approx(Z)
    assert trunk_top == pytest.approx(canopy_bottom, abs=0.05 * 8)


def test_plant_shapes_are_deterministic_and_varied() -> None:
    a = plant_geometry(Vegetation(id="birch_1", kind="tree", x=30, y=-10, size=8), BUILDING, Z)
    again = plant_geometry(Vegetation(id="birch_1", kind="tree", x=30, y=-10, size=8), BUILDING, Z)
    other = plant_geometry(Vegetation(id="birch_2", kind="tree", x=30, y=-10, size=8), BUILDING, Z)
    assert a.foliage == again.foliage and a.foliage != other.foliage


def test_plants_near_the_building_are_shrunk_or_left_out() -> None:
    near = plant_geometry(Vegetation(id="close", kind="tree", x=13, y=4, size=8), BUILDING, Z)
    assert near is not None and near.scale < 1
    reach = max(math.hypot(v[0] - 13, v[1] - 4) for v in near.foliage.vertices)
    assert 13 - reach >= BUILDING.x2 + CLEARANCE - 1e-6  # the whole canopy stays clear, jitter included
    assert plant_geometry(Vegetation(id="touching", kind="tree", x=10.3, y=4, size=8), BUILDING, Z) is None


@pytest.mark.parametrize("case", sorted(all_specs()))
def test_no_planting_reaches_the_building(case: str) -> None:
    spec = all_specs()[case]
    scene = compile_scene(spec)
    t, o = spec.building.wall_thickness / 2, spec.roof.overhang
    for element in scene.elements:
        if element.kind == "vegetation" and element.mesh is not None:
            for x, y, _ in element.mesh.vertices:
                inside = -t - o < x < spec.building.width + t + o and -t - o < y < spec.building.depth + t + o
                assert not inside, f"{element.name} reaches into the building"


def test_examples_have_site_and_planting_collections() -> None:
    scene = compile_scene(BuildingSpecification.model_validate(example()))
    parents = {c.name: c.parent for c in scene.collections}
    assert parents["SITE"] == "ENVIRONMENT" and parents["PLANTING"] == "ENVIRONMENT"
    names = {e.name for e in scene.elements}
    assert {"Site_Driveway", "Site_FrontPath", "Site_RearPatio", "Tree_TreeFront", "Tree_TreeFront_Trunk", "Hedge_HedgeRear"} <= names
    assert {m.recipe.value for m in scene.materials} >= {"foliage", "bark"}


def test_validator_warns_about_planting_that_will_be_shrunk_or_dropped() -> None:
    data = example()
    find(data["environment"]["vegetation"], "tree_front").update(x=11.0, y=4.0)   # beside the right wall
    find(data["environment"]["vegetation"], "hedge_rear").update(x=4.0, y=8.9)    # against the rear wall
    messages = [i.message for i in validate_specification(BuildingSpecification.model_validate(data)).report.issues
                if i.code == "planting_too_close"]
    assert any("tree_front" in m and "drawn" in m for m in messages)
    assert any("hedge_rear" in m and "left out" in m for m in messages)


def test_plant_reach_by_kind() -> None:
    assert plant_radius(Vegetation(id="t", kind="tree", x=0, y=0, size=10)) == pytest.approx(3.2 * 1.12)
    assert plant_radius(Vegetation(id="h", kind="hedge", x=0, y=0, size=1.5)) == pytest.approx(math.hypot(1.25, 0.35))
