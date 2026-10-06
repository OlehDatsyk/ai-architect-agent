"""BuildingSpecification -> SceneSpec.

Heights (per floor at elevation e, floor-to-floor height h, slab thickness s):
    exterior walls   e .. e + h          (they cover the slab edge)
    interior walls   e .. e + h - s      (clear room height, as in the specification)
    slab above floor e + h - s .. e + h  (the next floor's structure, or the roof deck)
    ground slab      -foundation .. 0    (spans the outer face of the exterior walls)
    room floors      e .. e + 0.02       (finish surface inside the walls)
    roof             on top of the highest wall plate, with gable infill where needed
"""

from app.geometry.placement import balcony_segment
from app.geometry.rect import Rect
from app.geometry.roof import ridge_axis
from app.models.building import BuildingSpecification
from app.models.common import Side
from app.models.materials import MaterialId, MaterialRef
from app.models.opening import Door, DoorType
from app.scene.cameras import exterior_cameras, floor_plan_camera, interior_cameras
from app.scene.landscape import plant_geometry, site_surfaces
from app.scene.lighting import ceiling_lights, presets
from app.scene.model import (
    Box3,
    SceneCamera,
    SceneCollection,
    SceneElement,
    SceneLight,
    SceneMaterial,
    SceneRecipe,
    SceneRender,
    SceneSpec,
    SceneViewLayer,
    SceneWorld,
    union,
)
from app.scene.naming import NameRegistry, camel, floor_word
from app.scene.openings import door_parts, openings_for_run, wall_pieces, window_parts
from app.scene.roof import roof_geometry
from app.scene.shapes import rect_box, subtract
from app.scene.stairs import stair_steps, stairwell
from app.scene.walls import TOL, WallRun, exterior_runs, interior_runs

FINISH_THICKNESS = 0.02
INWARD = {Side.FRONT: "+y", Side.REAR: "-y", Side.LEFT: "+x", Side.RIGHT: "-x"}
GROUND_MARGIN = 20.0
BALCONY_SLAB = 0.2
RAILING = 0.04

# Base colours (linear RGB) for each procedural recipe, unless the specification overrides them.
BASE_COLOURS: dict[MaterialId, tuple[float, float, float]] = {
    MaterialId.BRICK: (0.42, 0.14, 0.08), MaterialId.WHITE_RENDER: (0.85, 0.84, 0.80),
    MaterialId.CONCRETE: (0.45, 0.45, 0.43), MaterialId.TIMBER_CLADDING: (0.30, 0.18, 0.09),
    MaterialId.DARK_METAL: (0.05, 0.05, 0.06), MaterialId.PAINTED_PLASTER: (0.80, 0.79, 0.76),
    MaterialId.WOOD_FLOORING: (0.45, 0.28, 0.14), MaterialId.CARPET: (0.38, 0.36, 0.34),
    MaterialId.TILE: (0.70, 0.71, 0.70), MaterialId.SLATE: (0.12, 0.13, 0.15),
    MaterialId.CLAY_TILE: (0.45, 0.16, 0.08), MaterialId.STANDING_SEAM_METAL: (0.18, 0.19, 0.20),
    MaterialId.FLAT_ROOFING: (0.10, 0.10, 0.10), MaterialId.GLASS: (0.60, 0.72, 0.78),
    MaterialId.ALUMINIUM: (0.60, 0.61, 0.62), MaterialId.WOOD: (0.40, 0.25, 0.12),
    MaterialId.GRASS: (0.12, 0.25, 0.06), MaterialId.GRAVEL: (0.50, 0.48, 0.44), MaterialId.PAVING: (0.55, 0.54, 0.50),
}


def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


class _Builder:
    def __init__(self, spec: BuildingSpecification) -> None:
        self.spec = spec
        self.names = NameRegistry()
        self.materials: dict[str, SceneMaterial] = {}
        self.elements: list[SceneElement] = []
        self.collections = [SceneCollection(name="BUILDING"), SceneCollection(name="ENVIRONMENT")]
        self.room_names = {r.id: camel(r.name) for r in spec.rooms}
        self.cameras: list[SceneCamera] = []
        self.lights: list[SceneLight] = []
        self.worlds: list[SceneWorld] = []
        self.view_layers: list[SceneViewLayer] = []
        self.render = SceneRender()

    def material(self, ref: MaterialRef | None, fallback: MaterialId) -> str:
        ref = ref or MaterialRef(id=fallback)
        key = f"MAT_{camel(ref.id.value)}" + (f"_{ref.colour[1:].upper()}" if ref.colour else "")
        if key not in self.materials:
            if ref.colour:
                rgb = tuple(_srgb_to_linear(int(ref.colour[i:i + 2], 16) / 255) for i in (1, 3, 5))
            else:
                rgb = BASE_COLOURS[ref.id]
            self.materials[key] = SceneMaterial(name=key, recipe=ref.id, base_color=rgb, roughness=0.05 if ref.id is MaterialId.GLASS else 0.7)  # type: ignore[arg-type]
        return key

    def recipe_material(self, recipe: str, rgb: tuple[float, float, float]) -> str:
        key = f"MAT_{camel(recipe)}"
        if key not in self.materials:
            self.materials[key] = SceneMaterial(name=key, recipe=SceneRecipe(recipe), base_color=rgb)
        return key

    def add(self, **fields) -> None:
        self.elements.append(SceneElement(**fields))

    def collection(self, name: str, parent: str | None) -> str:
        if not any(c.name == name for c in self.collections):
            self.collections.append(SceneCollection(name=name, parent=parent))
        return name


def compile_scene(spec: BuildingSpecification) -> SceneSpec:
    s = _Builder(spec)
    b, ext = spec.building, spec.exterior
    ext_t, int_t, slab = b.wall_thickness, b.interior_wall_thickness, b.slab_thickness
    half_ext = ext_t / 2
    floors = sorted(spec.floors, key=lambda f: f.level)
    floor_z = {f.level: f.elevation for f in floors}

    s.add(kind="ground", name=s.names.unique("Ground"), collection="ENVIRONMENT",
          boxes=[Box3(min=(-GROUND_MARGIN, -GROUND_MARGIN, -b.foundation_height - 0.05),
                      max=(b.width + GROUND_MARGIN, b.depth + GROUND_MARGIN, -b.foundation_height))],
          material=s.material(spec.environment.ground_material, MaterialId.GRASS))
    s.add(kind="slab", name=s.names.unique("Slab_GroundFloor"), collection=s.collection("FLOOR_0", "BUILDING"),
          boxes=[Box3(min=(-half_ext, -half_ext, -b.foundation_height), max=(b.width + half_ext, b.depth + half_ext, 0.0))],
          material=s.material(None, MaterialId.CONCRETE), tags={"role": "ground_slab"})

    wells_from = {f.level: [stairwell(st) for st in spec.stairs if st.from_floor == f.level] for f in floors}
    wells_to = {f.level: [stairwell(st) for st in spec.stairs if st.to_floor == f.level] for f in floors}

    for floor in floors:
        level, e, h = floor.level, floor.elevation, floor.height
        coll = s.collection(f"FLOOR_{level}", "BUILDING")
        walls_c, rooms_c = s.collection(f"WALLS_{level}", coll), s.collection(f"ROOMS_{level}", coll)
        doors_c, windows_c = s.collection(f"DOORS_{level}", coll), s.collection(f"WINDOWS_{level}", coll)
        word = floor_word(level)
        rooms = spec.rooms_on_floor(level)
        rects = [Rect(r.x, r.y, r.width, r.depth) for r in rooms]

        runs = [(run, e + h, "exterior") for run in exterior_runs(b.width, b.depth, ext_t)]
        runs += [(run, e + h - slab, "interior") for run in interior_runs(rects, b.width, b.depth, ext_t, int_t)]
        for run, top, wall_type in runs:
            openings = openings_for_run(run, spec, level, e, top)
            label = run.side.value.capitalize() if run.side else "Interior"
            tags = {"wall_type": wall_type, "floor": str(level), "axis": run.axis.value, "openings": str(len(openings))}
            if run.side:
                tags["side"] = run.side.value
            inner = {"inner_material": s.material(None, MaterialId.PAINTED_PLASTER), "inward": INWARD[run.side]} if run.side else {}
            s.add(kind="wall", name=s.names.numbered(f"Wall_{word}_{label}"), collection=walls_c, tags=tags,
                  boxes=wall_pieces(run, e, top, openings),
                  material=s.material(ext.wall_material if run.side else None, MaterialId.PAINTED_PLASTER), **inner)
            for op in openings:
                _add_opening(s, op, run, level, doors_c, windows_c)

        for room, rect in zip(rooms, rects):
            inset = _insets(rect, b.width, b.depth, half_ext, int_t / 2)
            inner = Rect(rect.x + inset["left"], rect.y + inset["front"],
                         rect.width - inset["left"] - inset["right"], rect.depth - inset["front"] - inset["rear"])
            s.add(kind="room_floor", name=s.names.unique(f"Room_{camel(room.name)}"), collection=rooms_c,
                  boxes=[rect_box(p, e, e + FINISH_THICKNESS) for p in subtract(inner, wells_to[level])],
                  material=s.material(room.floor_material, MaterialId.WOOD_FLOORING),
                  tags={"room_id": room.id, "room_type": room.type.value, "floor": str(level)})

        above = "RoofDeck" if level == floors[-1].level else floor_word(level + 1)
        slab_rect = Rect(half_ext, half_ext, b.width - ext_t, b.depth - ext_t)
        s.add(kind="slab", name=s.names.unique(f"Slab_{above}"), collection=s.collection(f"CEILING_{level}", coll),
              boxes=[rect_box(p, e + h - slab, e + h) for p in subtract(slab_rect, wells_from[level])],
              material=s.material(None, MaterialId.CONCRETE),
              tags={"role": "roof_deck" if above == "RoofDeck" else "floor_slab"})

    if spec.stairs:
        stairs_c = s.collection("STAIRS", "BUILDING")
        for st in spec.stairs:
            s.add(kind="stair", name=s.names.unique(f"Stairs_{floor_word(st.from_floor)}To{floor_word(st.to_floor)}"),
                  collection=stairs_c, boxes=stair_steps(st, floor_z[st.from_floor], FINISH_THICKNESS),
                  material=s.material(None, MaterialId.WOOD), tags={"from_floor": str(st.from_floor), "to_floor": str(st.to_floor)})

    _add_balconies(s, half_ext, floor_z)

    _add_landscape(s, half_ext)

    z_top = max(f.elevation + f.height for f in floors)
    ridge = ridge_axis(spec.roof, b.width, b.depth)
    boxes, mesh, infills = roof_geometry(spec.roof, ridge, b.width, b.depth, ext_t, z_top)
    roof_c = s.collection("ROOF", "BUILDING")
    s.add(kind="roof", name=s.names.unique(f"Roof_{spec.roof.type.value.capitalize()}"), collection=roof_c,
          boxes=boxes, mesh=mesh, material=s.material(spec.roof.material, MaterialId.SLATE),
          tags={"roof_type": spec.roof.type.value, "pitch": f"{spec.roof.pitch:g}"})
    for infill in infills:
        s.add(kind="wall", name=s.names.numbered("Wall_RoofInfill"), collection=roof_c, mesh=infill,
              material=s.material(ext.wall_material, MaterialId.BRICK), tags={"wall_type": "roof_infill"})

    _add_cameras_and_lighting(s, floors)
    return SceneSpec(project_name=spec.project.name, collections=s.collections, materials=list(s.materials.values()),
                     elements=s.elements, cameras=s.cameras, lights=s.lights, worlds=s.worlds,
                     view_layers=s.view_layers, render=s.render)


def _add_cameras_and_lighting(s: "_Builder", floors) -> None:
    spec = s.spec
    building = [b for e in s.elements if e.kind not in ("ground", "site", "vegetation") for b in ([e.mesh.bounds()] if e.mesh else e.boxes)]
    bounds = union(building)
    aspect = s.render.aspect
    s.collection("CAMERAS", None)
    s.cameras = exterior_cameras(bounds, aspect) + interior_cameras(spec, aspect)
    outer = Rect(bounds.min[0], bounds.min[1], bounds.max[0] - bounds.min[0], bounds.max[1] - bounds.min[1])
    for floor in floors:
        word = floor_word(floor.level).replace("Floor", "")
        plan = floor_plan_camera(f"Camera_FloorPlan_{word}", floor.level, spec, aspect, outer)
        # Record which view layer this camera is meant for, so renderers never have to guess from names.
        s.cameras.append(plan.model_copy(update={"tags": {**plan.tags, "view_layer": f"FloorPlan_{word}"}}))
        above = [f"FLOOR_{f.level}" for f in floors if f.level > floor.level]
        s.view_layers.append(SceneViewLayer(name=f"FloorPlan_{word}", exclude=["ROOF", f"CEILING_{floor.level}", *above]))

    for name, parent in (("LIGHTS", None), ("LIGHTS_DAY", "LIGHTS"), ("LIGHTS_EVENING", "LIGHTS"), ("LIGHTS_INTERIOR", "LIGHTS")):
        s.collection(name, parent)
    s.worlds, suns = presets(spec)
    s.lights = suns + ceiling_lights(spec, lambda base: s.names.numbered(f"Light_{camel(base[6:])}"))
    s.render = SceneRender(active_camera="Camera_Exterior_Front", active_world="World_Day", hidden_collections=["LIGHTS_EVENING"])


FOLIAGE_COLOUR = (0.05, 0.16, 0.03)
BARK_COLOUR = (0.12, 0.08, 0.05)


def _add_landscape(s: _Builder, half_ext: float) -> None:
    """Driveway, patio and paths on the ground; trees, shrubs and hedges around the building."""
    b, env = s.spec.building, s.spec.environment
    z_ground = -b.foundation_height
    # The plinth (ground slab) runs to the outer face of the walls; roofs overhang a little further.
    building = Rect(-half_ext, -half_ext, b.width + 2 * half_ext, b.depth + 2 * half_ext)
    ground = Rect(-GROUND_MARGIN, -GROUND_MARGIN, b.width + 2 * GROUND_MARGIN, b.depth + 2 * GROUND_MARGIN)
    areas = [a for a in (env.driveway, env.patio, *env.paths) if a is not None]
    if areas:
        site_c = s.collection("SITE", "ENVIRONMENT")
        for area, boxes in site_surfaces(areas, building, ground, z_ground):
            s.add(kind="site", name=s.names.unique(f"Site_{camel(area.id)}"), collection=site_c, boxes=boxes,
                  material=s.material(area.material, MaterialId.PAVING), tags={"site_id": area.id})
    if env.vegetation:
        planting_c = s.collection("PLANTING", "ENVIRONMENT")
        reach = Rect(building.x - s.spec.roof.overhang, building.y - s.spec.roof.overhang,
                     building.width + 2 * s.spec.roof.overhang, building.depth + 2 * s.spec.roof.overhang)
        for plant in env.vegetation:
            geometry = plant_geometry(plant, reach, z_ground)
            if geometry is None:
                continue  # too close to the building; the validator warns about this
            name = s.names.unique(f"{plant.kind.value.capitalize()}_{camel(plant.id)}")
            tags = {"plant_id": plant.id, "plant_kind": plant.kind.value, "scale": f"{geometry.scale:.2f}"}
            foliage = geometry.foliage
            s.add(kind="vegetation", name=name, collection=planting_c, material=s.recipe_material("foliage", FOLIAGE_COLOUR),
                  tags={**tags, "part": "foliage"}, **({"boxes": [foliage]} if isinstance(foliage, Box3) else {"mesh": foliage}))
            if geometry.trunk is not None:
                s.add(kind="vegetation", name=s.names.unique(f"{name}_Trunk"), collection=planting_c, mesh=geometry.trunk,
                      material=s.recipe_material("bark", BARK_COLOUR), tags={**tags, "part": "trunk"})


def _add_opening(s: _Builder, op, run: WallRun, level: int, doors_c: str, windows_c: str) -> None:
    ext = s.spec.exterior
    if isinstance(op.source, Door):
        door = op.source
        frame, leaf = door_parts(op, run)
        if not frame:
            return
        a = s.room_names.get(door.connects_room_a, "Room")
        b = s.room_names.get(door.connects_room_b or "", door.type.value.capitalize().replace("_", ""))
        name = s.names.numbered(f"Door_{a}_{b}")
        glazed = door.type is DoorType.PATIO_SLIDING
        frame_mat = s.material(ext.window_frame_material if glazed else None, MaterialId.WOOD)
        leaf_mat = s.material(MaterialRef(id=MaterialId.GLASS) if glazed else (ext.door_material if door.is_external else door.material), MaterialId.WOOD)
        tags = {"door_id": door.id, "door_type": door.type.value, "floor": str(level)}
        s.add(kind="door", name=name, collection=doors_c, boxes=frame, material=frame_mat, tags={**tags, "part": "frame"})
        s.add(kind="door", name=s.names.unique(f"{name}_Leaf"), collection=doors_c, boxes=leaf, material=leaf_mat, tags={**tags, "part": "leaf"})
    else:
        window = op.source
        frame, glass = window_parts(op, run)
        name = s.names.numbered(f"Window_{s.room_names.get(window.room, 'Room')}")
        tags = {"window_id": window.id, "style": window.style.value, "floor": str(level)}
        s.add(kind="window", name=name, collection=windows_c, boxes=frame,
              material=s.material(ext.window_frame_material, MaterialId.ALUMINIUM), tags={**tags, "part": "frame"})
        s.add(kind="window", name=s.names.unique(f"{name}_Glass"), collection=windows_c, boxes=glass,
              material=s.material(MaterialRef(id=MaterialId.GLASS), MaterialId.GLASS), tags={**tags, "part": "glass"})


def _add_balconies(s: _Builder, half_ext: float, floor_z: dict[int, float]) -> None:
    spec = s.spec
    b = spec.building
    footprint = Rect(0, 0, b.width, b.depth)
    rooms = {r.id: r for r in spec.rooms}
    for balcony in spec.balconies:
        room = rooms.get(balcony.room)
        if room is None:
            continue
        e = floor_z[room.floor]
        seg = balcony_segment(balcony, footprint)
        a, c, d = seg.start, seg.end, balcony.depth
        if balcony.wall is Side.REAR:
            plan = Rect(a, b.depth + half_ext, c - a, d)
        elif balcony.wall is Side.FRONT:
            plan = Rect(a, -half_ext - d, c - a, d)
        elif balcony.wall is Side.LEFT:
            plan = Rect(-half_ext - d, a, d, c - a)
        else:
            plan = Rect(b.width + half_ext, a, d, c - a)
        coll = s.collection(f"BALCONIES_{room.floor}", f"FLOOR_{room.floor}")
        name = s.names.unique(f"Balcony_{camel(room.name)}")
        s.add(kind="balcony", name=name, collection=coll, boxes=[rect_box(plan, e - BALCONY_SLAB, e)],
              material=s.material(balcony.floor_material, MaterialId.CONCRETE), tags={"balcony_id": balcony.id, "part": "slab"})
        z1 = e + balcony.railing_height
        r = RAILING
        outward = {Side.REAR: "y2", Side.FRONT: "y", Side.LEFT: "x", Side.RIGHT: "x2"}[balcony.wall]
        if outward in ("y", "y2"):
            edge_y = plan.y2 - r if outward == "y2" else plan.y
            near_y0, near_y1 = (plan.y, plan.y2 - r) if outward == "y2" else (plan.y + r, plan.y2)
            rails = [Rect(plan.x, edge_y, plan.width, r), Rect(plan.x, near_y0, r, near_y1 - near_y0), Rect(plan.x2 - r, near_y0, r, near_y1 - near_y0)]
        else:
            edge_x = plan.x2 - r if outward == "x2" else plan.x
            near_x0, near_x1 = (plan.x, plan.x2 - r) if outward == "x2" else (plan.x + r, plan.x2)
            rails = [Rect(edge_x, plan.y, r, plan.depth), Rect(near_x0, plan.y, near_x1 - near_x0, r), Rect(near_x0, plan.y2 - r, near_x1 - near_x0, r)]
        s.add(kind="balcony", name=s.names.unique(f"{name}_Railing"), collection=coll, boxes=[rect_box(p, e, z1) for p in rails],
              material=s.material(balcony.railing_material, MaterialId.GLASS), tags={"balcony_id": balcony.id, "part": "railing"})


def _insets(rect: Rect, width: float, depth: float, half_ext: float, half_int: float) -> dict[str, float]:
    """How far each edge of a room's floor finish sits inside its walls."""
    return {
        "left": half_ext if abs(rect.x) <= TOL else half_int,
        "right": half_ext if abs(rect.x2 - width) <= TOL else half_int,
        "front": half_ext if abs(rect.y) <= TOL else half_int,
        "rear": half_ext if abs(rect.y2 - depth) <= TOL else half_int,
    }
