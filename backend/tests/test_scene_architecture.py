"""Openings, doors, windows, stairs, stairwells, balconies and roofs in the compiled scene."""

from collections import Counter, defaultdict

import pytest

from app.geometry.placement import door_segment, window_segment
from app.geometry.rect import Rect
from app.geometry.stairs import stair_footprint
from app.models import BuildingSpecification, DoorType, RoofType
from app.models.common import Axis
from app.scene.compiler import compile_scene
from app.scene.model import MeshData
from app.scene.roof import roof_geometry
from app.scene.shapes import subtract
from tests.helpers import example
from tests.scene_cases import all_specs


def spec_of(slug: str = "british-family-house") -> BuildingSpecification:
    return BuildingSpecification.model_validate(example(slug))


def inside_any(point: tuple[float, float, float], boxes) -> bool:
    return any(all(b.min[i] + 1e-6 < point[i] < b.max[i] - 1e-6 for i in range(3)) for b in boxes)


@pytest.mark.parametrize("case", sorted(all_specs()))
def test_every_door_and_window_is_built_and_its_opening_is_clear(case: str) -> None:
    spec = all_specs()[case]
    scene = compile_scene(spec)
    floor_z = {f.level: f.elevation for f in spec.floors}
    room_floor = {r.id: r.floor for r in spec.rooms}
    footprint = Rect(0, 0, spec.building.width, spec.building.depth)
    walls = [b for e in scene.elements if e.kind == "wall" for b in e.boxes]

    built_doors = Counter(e.tags["door_id"] for e in scene.elements if e.kind == "door")
    built_windows = Counter(e.tags["window_id"] for e in scene.elements if e.kind == "window")
    for door in spec.doors:
        assert built_doors[door.id] == (0 if door.type is DoorType.OPENING else 2), door.id  # frame + leaf
        seg = door_segment(door)
        mid = (seg.start + seg.end) / 2
        x, y = (mid, seg.coord) if seg.axis is Axis.X else (seg.coord, mid)
        assert not inside_any((x, y, floor_z[door.floor] + 1.0), walls), f"door {door.id} is walled up"
    for window in spec.windows:
        assert built_windows[window.id] == 2, window.id  # frame + glass
        seg = window_segment(window, footprint)
        mid = (seg.start + seg.end) / 2
        x, y = (mid, seg.coord) if seg.axis is Axis.X else (seg.coord, mid)
        z = floor_z[room_floor[window.room]] + window.sill_height + window.height / 2
        assert not inside_any((x, y, z), walls), f"window {window.id} is walled up"


def test_walls_are_solid_away_from_openings() -> None:
    scene = compile_scene(spec_of())
    front = next(e for e in scene.elements if e.name == "Wall_GroundFloor_Front_01")
    assert len(front.boxes) > 1
    assert inside_any((9.5, 0.0, 1.0), front.boxes)  # solid near the right-hand corner


@pytest.mark.parametrize("case", sorted(all_specs()))
def test_stairs_climb_to_the_next_floor_through_a_stairwell(case: str) -> None:
    spec = all_specs()[case]
    scene = compile_scene(spec)
    floor_z = {f.level: f.elevation for f in spec.floors}
    stairs = [e for e in scene.elements if e.kind == "stair"]
    assert len(stairs) == len(spec.stairs)
    for st, element in zip(spec.stairs, stairs):
        assert len(element.boxes) == st.risers - 1
        top = max(b.max[2] for b in element.boxes)
        assert top == pytest.approx(floor_z[st.to_floor] - st.rise, abs=1e-3)
        fp = stair_footprint(st)
        probe = (fp.x + fp.width / 2, fp.y + fp.depth / 2, floor_z[st.to_floor] - 0.1)  # inside the slab zone
        slabs = [b for e in scene.elements if e.kind == "slab" for b in e.boxes]
        assert not inside_any(probe, slabs), "no stairwell in the slab above"


def test_balcony_projects_outside_the_rear_wall() -> None:
    spec = spec_of("luxury-house")
    scene = compile_scene(spec)
    slab = next(e for e in scene.elements if e.kind == "balcony" and e.tags["part"] == "slab")
    rail = next(e for e in scene.elements if e.kind == "balcony" and e.tags["part"] == "railing")
    t = spec.building.wall_thickness
    assert slab.bounds.min[1] == pytest.approx(spec.building.depth + t / 2)
    assert slab.bounds.max[1] == pytest.approx(spec.building.depth + t / 2 + 1.5)
    assert len(rail.boxes) == 3 and rail.bounds.max[2] - slab.bounds.max[2] == pytest.approx(1.1)


def test_subtract_leaves_the_hole_and_nothing_else() -> None:
    pieces = subtract(Rect(0, 0, 10, 8), [Rect(3, 2, 2, 4)])
    assert sum(p.area for p in pieces) == pytest.approx(80 - 8)
    assert all(p.intersection_area(Rect(3, 2, 2, 4)) == 0 for p in pieces)


# ----------------------------------------------------------------------------- roofs

def closed_and_outward(mesh: MeshData) -> tuple[bool, float]:
    """Every edge used once in each direction (closed, consistently wound) and the signed volume."""
    edges: dict[tuple[int, int], int] = defaultdict(int)
    for face in mesh.faces:
        for a, b in zip(face, face[1:] + face[:1]):
            edges[(a, b)] += 1
    closed = all(n == 1 and edges.get((b, a)) == 1 for (a, b), n in edges.items())
    volume = 0.0
    v = mesh.vertices
    for face in mesh.faces:  # fan triangulation, divergence theorem
        for i in range(1, len(face) - 1):
            (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = v[face[0]], v[face[i]], v[face[i + 1]]
            volume += (x1 * (y2 * z3 - y3 * z2) - x2 * (y1 * z3 - y3 * z1) + x3 * (y1 * z2 - y2 * z1)) / 6
    return closed, volume


@pytest.mark.parametrize("roof_type", ["gable", "hip", "shed"])
@pytest.mark.parametrize("ridge", [Axis.X, Axis.Y])
@pytest.mark.parametrize("size", [(12, 8), (8, 12), (10, 10)])
def test_pitched_roofs_and_infills_are_closed_outward_meshes(roof_type: str, ridge: Axis, size: tuple[int, int]) -> None:
    from app.models import MaterialRef, Roof

    roof = Roof(type=RoofType(roof_type), pitch=35, overhang=0.3, material=MaterialRef(id="slate"), ridge_direction=ridge)
    _, mesh, infills = roof_geometry(roof, ridge, size[0], size[1], 0.3, 5.4)
    assert mesh is not None
    for m in [mesh, *infills]:
        closed, volume = closed_and_outward(m)
        assert closed and volume > 0


def test_roof_underside_meets_the_wall_tops() -> None:
    spec = spec_of()
    scene = compile_scene(spec)
    roof = next(e for e in scene.elements if e.kind == "roof")
    z_top = max(f.elevation + f.height for f in spec.floors)
    lowest_over_walls = min(v[2] for v in roof.mesh.vertices)
    assert lowest_over_walls < z_top  # eaves hang below the wall plate...
    infills = [e for e in scene.elements if e.tags.get("wall_type") == "roof_infill"]
    assert len(infills) == 2 and all(e.bounds.min[2] == pytest.approx(z_top) for e in infills)  # ...and the gables sit on it


def test_flat_roof_is_a_slab_over_the_walls() -> None:
    spec = spec_of("modern-bungalow")
    roof = next(e for e in compile_scene(spec).elements if e.kind == "roof")
    assert roof.mesh is None and len(roof.boxes) == 1
    assert roof.bounds.min[2] == pytest.approx(spec.floors[0].height)
