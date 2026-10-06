import re

import pytest

from app.models import BuildingSpecification
from app.scene.compiler import compile_scene
from app.scene.model import Box3
from app.scene.naming import NameRegistry, camel
from tests.helpers import example
from tests.scene_cases import all_specs


def scene_for(slug: str = "british-family-house"):
    return compile_scene(BuildingSpecification.model_validate(example(slug)))


def test_names_are_readable_unique_and_safe() -> None:
    scene = scene_for()
    names = [e.name for e in scene.elements]
    assert len(names) == len(set(names))
    assert "Wall_GroundFloor_Front_01" in names and "Room_MasterBedroom" in names and "Slab_RoofDeck" in names
    assert not any(re.search(r"\.\d{3}$", n) for n in names)  # no Cube.001-style names


def test_camel_and_registry() -> None:
    assert camel("Kitchen / Dining") == "KitchenDining"
    assert camel("<script>alert(1)</script>") == "ScriptAlert1Script"
    registry = NameRegistry()
    assert [registry.unique("Room_Bedroom"), registry.unique("Room_Bedroom")] == ["Room_Bedroom", "Room_Bedroom_02"]
    assert registry.numbered("Wall_X") == "Wall_X_01" and registry.numbered("Wall_X") == "Wall_X_02"


def test_collections_follow_floors() -> None:
    scene = scene_for()
    parents = {c.name: c.parent for c in scene.collections}
    assert parents["FLOOR_0"] == "BUILDING" and parents["WALLS_1"] == "FLOOR_1" and parents["ENVIRONMENT"] is None
    assert {e.collection for e in scene.elements if e.kind == "wall" and e.tags.get("wall_type") != "roof_infill"} == {"WALLS_0", "WALLS_1"}
    assert {e.collection for e in scene.elements if e.tags.get("wall_type") == "roof_infill"} == {"ROOF"}


def test_heights_follow_the_specification() -> None:
    spec = BuildingSpecification.model_validate(example())
    scene = compile_scene(spec)
    by = {e.name: e for e in scene.elements}
    assert by["Wall_GroundFloor_Front_01"].bounds.min[2] == 0 and by["Wall_GroundFloor_Front_01"].bounds.max[2] == 2.7
    interior = by["Wall_GroundFloor_Interior_01"].bounds
    assert interior.max[2] == pytest.approx(2.7 - spec.building.slab_thickness)
    assert by["Slab_FirstFloor"].bounds.min[2] == pytest.approx(2.45) and by["Slab_FirstFloor"].bounds.max[2] == pytest.approx(2.7)
    assert by["Wall_FirstFloor_Rear_01"].bounds.max[2] == pytest.approx(5.3)
    assert by["Slab_GroundFloor"].bounds.min[2] == -spec.building.foundation_height


def test_overall_size_matches_footprint_plus_walls() -> None:
    spec = BuildingSpecification.model_validate(example())
    walls = [e.bounds for e in compile_scene(spec).elements if e.kind == "wall"]
    t = spec.building.wall_thickness
    assert min(b.min[0] for b in walls) == pytest.approx(-t / 2)
    assert max(b.max[0] for b in walls) == pytest.approx(spec.building.width + t / 2)
    assert max(b.max[1] for b in walls) == pytest.approx(spec.building.depth + t / 2)


def test_colour_override_creates_its_own_material() -> None:
    scene = scene_for()
    brick = next(m for m in scene.materials if m.name.startswith("MAT_Brick"))
    assert brick.name == "MAT_Brick_8C4A36"
    assert all(0 <= c <= 1 for c in brick.base_color)
    assert {e.material for e in scene.elements} <= {m.name for m in scene.materials}


def solid_boxes(scene) -> list[tuple[str, Box3]]:
    return [(e.name, box) for e in scene.elements if e.kind != "ground" for box in e.boxes]


def overlapping_boxes(scene) -> list[tuple[str, str]]:
    boxes = sorted(solid_boxes(scene), key=lambda item: item[1].min[0])
    clashes = []
    for i, (name_a, a) in enumerate(boxes):
        for name_b, b in boxes[i + 1:]:
            if b.min[0] >= a.max[0]:
                break  # sorted by x: nothing further along can overlap a
            if a.overlap_volume(b) > 1e-7:
                clashes.append((name_a, name_b))
    return clashes


@pytest.mark.parametrize("case", sorted(all_specs()))
def test_no_solid_boxes_overlap(case: str) -> None:
    """Walls, wall pieces, frames, leaves, glass, slabs, finishes, stairs and balconies never intersect."""
    assert overlapping_boxes(compile_scene(all_specs()[case])) == []


def test_every_material_names_its_recipe_and_overrides_keep_the_recipe() -> None:
    scene = scene_for()
    by_name = {m.name: m for m in scene.materials}
    assert by_name["MAT_Brick_8C4A36"].recipe.value == "brick"  # darker brick: same recipe, its own colour
    assert by_name["MAT_Glass"].recipe.value == "glass"
    assert all(m.name.startswith(f"MAT_{camel(m.recipe.value)}") for m in scene.materials)


def test_recipes_match_the_specification() -> None:
    spec = BuildingSpecification.model_validate(example("scandinavian-house"))
    recipes = {m.recipe.value for m in compile_scene(spec).materials}
    assert {"timber_cladding", "standing_seam_metal", "glass", "grass", "carpet"} <= recipes
