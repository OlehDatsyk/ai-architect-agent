# Blender integration

Blender runs as a separate process for each build. The backend sends it **data, never code**: a scene description that the runner turns into geometry with this repository's own generator functions.

```
BuildingSpecification
   │  validated again (errors stop here: nothing reaches Blender)
   ▼
scene compiler            backend/app/scene/      pure Python, unit-tested without Blender
   │  scene.json: named boxes, collections, materials
   ▼
job folder                output/jobs/<job_id>/
   │
   ▼
blender --background --factory-startup --python blender/scripts/runner.py -- <job_dir>
   │  scene_validation.py: whitelist of element kinds, finite bounded numbers, plain names
   │  scene_builder.py -> wall_generator, floor_generator, ground_generator, material_generator
   ▼
building.blend · result.json (every object's real bounds) · progress.jsonl · blender.log
```

## Why this design

- **No code crosses the boundary.** Claude never writes Blender Python, and neither does the backend. The runner accepts nine element kinds (`ground`, `slab`, `wall`, `room_floor`, `door`, `window`, `stair`, `balcony`, `roof`), each made of either axis-aligned boxes or an explicit mesh (vertices and face indices). It rejects anything else: unknown kinds, names that aren't plain identifiers, non-finite or out-of-range numbers, out-of-range or repeated face indices, oversized geometry, references to undefined collections or materials. A test sends a tampered scene to real Blender and checks it is refused.
- **Geometry is decided where it can be tested.** Wall runs, junctions, heights and insets are calculated by the backend compiler with ordinary pytest coverage. The Blender scripts only create what they are given, so they stay small and Blender-version-specific code stays in one place.
- **Each build is isolated.** A crash or hang in Blender affects one job, not the API process. Jobs time out (`BLENDER_TIMEOUT_SECONDS`, default 300).
- **Results are checked, not assumed.** The runner reports each object's real world-space bounds, collection and material in `result.json`. The real-Blender tests compare them with the scene description.

## Coordinates and heights

Metres throughout. Blender's axes are used unchanged: X is width, Y is depth with the front at y = 0, Z is up. Ground-floor finished floor level is z = 0.

| Element | Plan extent | Height (floor at elevation e, floor-to-floor h, slab s) |
| --- | --- | --- |
| Exterior walls | Centred on the footprint edge, 0.3 m thick; front and rear walls own the corners | e to e + h |
| Interior walls | Centred on shared room edges, 0.1 m thick; walls along X own junctions | e to e + h − s |
| Slab above each floor | Inside the exterior walls | e + h − s to e + h (the top one is the roof deck) |
| Ground-floor slab | To the outer face of the exterior walls | −foundation to 0 |
| Room floor finishes | Inside the room's walls | e to e + 0.02 |
| Ground | Footprint plus 20 m in every direction | Just below the foundation |
| Wall openings | The wall is split into solid pieces: full height between openings, a lintel above each, a sill wall below each window. Open-plan openings are full height. | Door: e to e + door height; window: sill to sill + height |
| Doors | Frame (two jambs and a head) filling the opening's reveal, plus a 40 mm leaf; patio doors have two offset glass panels | Inside the opening |
| Windows | 60 mm frame and sill, 20 mm glass; a centre mullion when wider than 1.4 m (except fixed lights) | Inside the opening |
| Stairs | One solid block per tread, rising from the floor finish; a flight of n risers has n − 1 treads | e + 0.02 to each tread top |
| Stairwells | The flight's footprint is cut out of the slab above and out of the landing's floor finish | |
| Balconies | 0.2 m slab projecting from the outer wall face, glass balustrade on three sides | Slab top at the floor level |
| Roof | Flat: a 0.25 m slab over walls and overhang. Gable, hip and shed: closed 0.2 m-thick meshes whose underside meets the wall tops along their outer face | From the highest wall plate |
| Roof infill | Gable ends and the high wall of a shed roof are closed with wall-material infill meshes | From the wall plate to the roof underside |

No two solid boxes overlap, including wall pieces, frames, leaves, glass, slabs, finishes, stairs and balconies. This is tested on the five examples, five planned intents and about 55 randomly generated planned buildings. The same buildings are checked for:

- every shared room edge having a wall;
- every door and window being built, with a clear opening (a probe through its centre hits no wall);
- every stair reaching the floor above through a stairwell.

Every roof type, in both ridge directions and for wide, deep and square plans, is checked to be a closed mesh with outward normals.

### Wall thickness in 2D validation

Walls in the specification are lines on room boundaries, but in 3D they are 0.3 m (exterior) and 0.1 m (interior) thick. Phase 6 exposed stairs and doors that fitted on the 2D plan but ran into a wall in 3D. Two validation rules (`stair_hits_wall`, `opening_hits_wall`) now use the same wall geometry as the scene compiler, so a specification that passes validation also builds without collisions. The planner keeps stairs clear of wall thickness at the side and end of the spine.

## Scene organisation

```
BUILDING
├── FLOOR_0
│   ├── Slab_GroundFloor
│   ├── CEILING_0    Slab_FirstFloor (the slab above this floor)
│   ├── WALLS_0      Wall_GroundFloor_Front_01, Wall_GroundFloor_Interior_03, ...
│   └── ROOMS_0      Room_EntranceHall, Room_KitchenDining, ...
├── FLOOR_1 ...
CAMERAS              Camera_Exterior_Front, Camera_Interior_LivingRoom, Camera_FloorPlan_Ground, ...
LIGHTS
├── LIGHTS_DAY       Sun_Day
├── LIGHTS_EVENING   Sun_Evening
└── LIGHTS_INTERIOR  Light_LivingRoom_01, ...
ENVIRONMENT          Ground
├── SITE             Site_Driveway, Site_FrontPath, Site_RearPatio
└── PLANTING         Tree_TreeFront, Tree_TreeFront_Trunk, Hedge_HedgeRear, ...
```

Doors, windows, stairs, balconies and the roof have their own collections (`DOORS_n`, `WINDOWS_n`, `BALCONIES_n`, `STAIRS`, `ROOF`). Doors and windows are two objects each, for example `Door_EntranceHall_Living_01` with `Door_EntranceHall_Living_01_Leaf`, and `Window_MasterBedroom_01` with `Window_MasterBedroom_01_Glass`.

Every object is a separate, editable mesh with its origin at its centre. It carries custom properties (`aiarch_kind`, `aiarch_floor`, `aiarch_side`, `aiarch_room_id`, ...) so later phases can find and update the right objects. Materials are shared, one per material and colour.

## Site and planting

| Element | How it is built |
| --- | --- |
| Driveway, patio, paths | 50 mm slabs on the ground in the specification's material, clipped so they never run under the building's plinth or under an earlier area (driveway first, then patio, then paths) and stay within the ground |
| Trees | A tapered octagonal trunk (bark) and a slightly irregular low-poly canopy (foliage, smooth-shaded), as two objects |
| Shrubs | A low, irregular mound sitting on the ground |
| Hedges | A clipped 2.5 m x 0.7 m box hedge as tall as specified |

Plant shapes are varied but **deterministic**: the irregularity is seeded from the plant's ID, so the same specification always produces the same garden. Proportions are fixed fractions of the specified height, shared by the validator and the geometry, so they always agree about size: a plant whose canopy would reach the building (including the roof overhang, with 0.3 m clearance) is drawn smaller, and one that would have to shrink to almost nothing is left out. The validator warns about both (`planting_too_close`).

Foliage and bark are **scene-only recipes**: they are used for planting but are not among the materials Claude can choose for the building.

## Cameras

Every camera is calculated by the backend from the building's real geometry (`backend/app/scene/cameras.py`), using the same camera model as Blender (36 mm sensor fitted to the wider image side, world +Z up).

| Camera | Placement |
| --- | --- |
| `Camera_Exterior_Front`, `_Rear`, `_Aerial` | Along a fixed viewing direction from the building's centre, at the **closest distance where every corner of the building's bounding box falls inside 88% of the frame** (found by bisection). Works for any building size. |
| `Camera_Interior_LivingRoom`, `_Kitchen`, `_MasterBedroom` | At eye height (1.55 m) in a room corner, 0.35 m from the walls, looking across to the opposite corner. The corner is chosen so the view faces the room's main windows. Roles fall back sensibly (an open-plan space serves as living room and kitchen, from different corners) and are skipped when no room fits. |
| `Camera_FloorPlan_Ground`, `_First`, ... | Orthographic, straight down, front of the building at the bottom of the image, sized to the whole footprint. |

**Floor-plan view layers.** Each floor has a view layer, `FloorPlan_Ground`, `FloorPlan_First` and so on, that excludes the roof, the floors above, and that floor's own ceiling slab (`CEILING_n`). Pick the view layer and its plan camera in Blender to render a clean plan; nothing is deleted from the scene. Each plan camera records its layer in the custom property `aiarch_view_layer`, so a renderer never has to infer it from names; a real-Blender test checks that the property names an existing layer that hides the roof.

`tests/blender/camera_check.py` reopens built files and uses Blender's own `world_to_camera_view` to confirm that exterior cameras see every corner of the building, interior cameras stand inside their rooms, and plan cameras see their floor's walls.

## Lighting presets

| Preset | World | Sun | Collections |
| --- | --- | --- | --- |
| **Day** (default) | `World_Day`: gradient sky from the specification's `sky` (clear, overcast or sunset) | `Sun_Day` from the specification's sun azimuth and elevation | `LIGHTS_DAY` |
| **Evening** | `World_Evening`: dusk sky | `Sun_Evening`: low (7°), warm, from the west | `LIGHTS_EVENING` (excluded from rendering by default) |

Interior ceiling lights (`LIGHTS_INTERIOR`) are warm area lights below each room's ceiling, in a row along the room's longer side for large rooms, with power scaled to floor area. Garages are left unlit.

To switch to evening in Blender: set the scene's world to `World_Evening`, enable rendering of `LIGHTS_EVENING` and disable `LIGHTS_DAY`. Rendering (Phase 10) will do this from a preset name.

The sky is built from basic nodes rather than Blender's Sky Texture, whose models changed between Blender 4 (`NISHITA`) and 5 (`SINGLE_SCATTERING` / `MULTIPLE_SCATTERING`), so it looks the same in every supported version. Sun azimuth is measured clockwise from +Y (taken as north, so the front faces south).

Both worlds are saved with a fake user. Blender drops unused data-blocks when saving, and without it the evening world silently disappeared from the file; a real-Blender test now checks the reopened file.

## Rendering

Renders are a separate step on a built job: `POST /api/designs/jobs/{job_id}/renders`. Every option comes from a fixed list, checked by the backend and again by `blender/scripts/render_runner.py` inside Blender:

| Option | Values |
| --- | --- |
| `camera` | Any camera the build created (the build response lists them) |
| `preset` | `day`, `evening` |
| `quality` | `preview` (16 samples, half resolution), `standard` (64 samples), `high` (256 Cycles / 128 EEVEE samples) |
| `resolution` | `1280x720`, `1920x1080`, `2560x1440` |
| `engine` | `auto` (default), `eevee`, `cycles` |

Images are saved as `output/jobs/<job_id>/renders/<render_id>.png` and served at `GET /api/designs/jobs/<job_id>/renders/<render_id>.png`. The app renders a preview of the front automatically after every build.

The runner applies the lighting preset with `lighting_presets.apply_preset` (the same function is usable from Blender's Python console), enables **exactly one view layer** (the camera's own floor-plan layer, or the main layer), and rejects blank images. A floor-plan camera without its view layer is an error rather than a fallback, because falling back would silently render the roof.

### Which engine `auto` chooses

The brief asks for EEVEE by default. EEVEE is the right choice on a machine with a GPU, but on servers without one it runs on a *software* OpenGL renderer and becomes far slower than Cycles. `auto` therefore tests the machine once per backend process, with a small scene containing brick and see-through glass:

1. If EEVEE cannot render, it uses **Cycles**.
2. If Blender reports a **software renderer** (`gpu.platform.renderer_get()` returns llvmpipe, softpipe, SwiftShader, lavapipe or Microsoft Basic Render Driver), it uses **Cycles**.
3. Otherwise it uses **EEVEE**, unless the test render shows EEVEE more than 1.5 times slower than Cycles.

Whenever `auto` does not use EEVEE, the render response includes a plain-English note saying why. Choosing `eevee` or `cycles` explicitly skips the test.

The renderer check came from measurement. A timing comparison alone was unreliable: on the development machine the same test gave EEVEE 28.0 s against Cycles 6.6 s on one run and 7.5 s against 4.2 s on another, close enough to the threshold to flip. Blender's own report of the OpenGL renderer (`llvmpipe` there, on both 4.2 and 5.2) is deterministic.

### Findings worth knowing

- **Headless EEVEE stalls when several view layers render at once.** With one view layer it renders normally (the full example house in 27 s even on software OpenGL). The runner always enables exactly one layer.
- **Glass in EEVEE** needs real transparency as well as transmission, otherwise windows render as opaque panels. Glass uses alpha with the *dithered* render method; the *blended* method stalled headless EEVEE.
- **Preview quality renders at half resolution**, where 10 mm mortar joints are thinner than a pixel and brickwork shows moiré bands at a distance. Standard and High render at full resolution, where the brickwork is clean.

### How long renders take

On the development machine (CPU only, Cycles), preview renders at 640 x 360 took 20 to 50 seconds; interiors are slower than exteriors because light bounces more indoors. Standard and High scale roughly with pixels x samples, so High at 1440p can take many minutes on a CPU. With a GPU, EEVEE renders take seconds. `RENDER_TIMEOUT_SECONDS` (default 900) bounds every render.

## Materials

Every material is procedural: built from Blender texture nodes, with no image files, so nothing depends on downloaded or copyrighted textures. The scene description names a **recipe** (one of the 19 material identifiers) and a base colour; the runner builds the node tree with the matching function in `blender/scripts/material_generator.py` and rejects any other recipe name.

| Recipe | How it is built |
| --- | --- |
| brick | 215 x 65 mm brick courses (stretcher bond) with 10 mm mortar joints, two-tone variation, recessed-joint bump |
| timber_cladding | 150 mm horizontal boards in staggered lengths, wood grain, board-gap bump |
| slate, clay_tile | Offset courses of tiles with shadowed joints |
| standing_seam_metal | Raised seams every 500 mm, metallic |
| tile, paving | Grout grids (300 mm tiles, 600 mm paving slabs) |
| wood_flooring | 190 mm planks in staggered lengths with grain |
| glass | Full transmission, IOR 1.45, near-zero roughness; blended transparency for EEVEE |
| white_render, concrete, painted_plaster, carpet, flat_roofing, grass | Noise-based colour variation and fine bump at a scale suited to each |
| gravel | Voronoi stones with bump |
| dark_metal, aluminium | Metallic with appropriate roughness |
| wood | Wood grain |

**Texture coordinates.** A house is many separate objects, so per-object coordinates would make bricks jump at every joint. Every recipe instead uses one shared node group, `AIARCH_WorldUV`, that projects **world-space position** onto each face according to its normal: along the wall and up for walls, x and y for floors, along the contour line for roof slopes. Courses therefore continue seamlessly across wall pieces, lintels and sills, and stay true to scale everywhere.

**Inside and outside of exterior walls.** Exterior wall objects have two material slots: the facade material and painted plaster for faces pointing into the building, so interiors are plastered while the outside stays brick, render or cladding. (Window and door reveals use the facade material.)

Colour overrides from the specification (for example `{"id": "brick", "colour": "#8c4a36"}`) set the recipe's base colour, so a darker brick is still brick.

## Setting it up

Set `BLENDER_EXECUTABLE` in `.env` to either:

- **A Blender application** (4.2 LTS or newer), for example:
  - Windows: `C:\Program Files\Blender Foundation\Blender 4.2\blender.exe`
  - macOS: `/Applications/Blender.app/Contents/MacOS/Blender`
  - Linux: `/usr/bin/blender`
- **A Python interpreter with Blender's `bpy` module installed**, useful for CI and headless servers. The current `bpy` (5.2) needs Python 3.13:

  ```bash
  python3.13 -m venv .blender-venv
  .blender-venv/bin/pip install bpy
  # BLENDER_EXECUTABLE=/absolute/path/to/.blender-venv/bin/python
  ```

`BLENDER_MODE=auto` (the default) treats an executable whose name starts with `python` as the second kind. The System panel in the app shows whether Blender was found.

All 19 real-Blender tests pass on **Blender 4.2.0 LTS** (Python 3.11) and **Blender 5.2.2 LTS** (Python 3.13), both run through the `bpy` module. The full backend suite also passes on Python 3.13.

## Testing

| Suite | Needs Blender | What it checks |
| --- | --- | --- |
| `tests/test_scene_walls.py` | No | Junction rules (T, cross, L), merging, no overlaps and full wall coverage across ~65 buildings |
| `tests/test_scene_compiler.py` | No | Names, collections, heights, overall size, materials, no overlapping solids |
| `tests/test_blender_runner_validation.py` | No | The runner rejects 14 kinds of malformed or malicious scene |
| `tests/test_blender_service.py` | No | Jobs with stand-in executables that succeed, fail, crash, hang or save nothing |
| `tests/test_scene_landscape.py` | No | Site areas on the ground and off the plinth, overlap precedence, closed outward plant meshes, determinism, shrinking near the building, validator warnings |
| `tests/test_scene_cameras_lighting.py` | No | Exterior cameras frame ~65 buildings snugly, interior cameras inside their rooms, plan cameras and view layers, presets, sun direction convention, ceiling lights, plastered inner faces |
| `tests/test_scene_architecture.py` | No | Openings clear, doors and windows built, stairs and stairwells, balconies, closed outward roof meshes for every type and orientation |
| `tests/test_render_settings.py`, `test_render_service.py`, `test_api_render.py` | No | Render option whitelists (including path-traversal attempts), the engine choice on six kinds of machine, timeouts, failures, endpoints |
| `tests/blender/test_real_blender.py` | **Yes** | Builds 10 buildings in real Blender and checks every object's bounds, collection and material, and that every mesh is closed with outward normals. Every material must be wired to its output, use the shared texture coordinates and contain no image or script nodes; glass must transmit. A built house is rendered with Cycles; day, evening and floor-plan renders go through the real render service (evening must be darker than day, and the plan must use its own view layer). A tampered scene is refused. |

```bash
BLENDER_EXECUTABLE=/path/to/blender python -m pytest tests/blender -v
```

During development the saved `.blend` files were also reopened in a fresh Blender process and rendered top-down, floor by floor, then compared with the planner's SVG plans to confirm that scale and positions match room for room.

## Current scope

The scene contains the structure (ground, slabs with stairwells, walls with openings, room floor finishes), doors, windows, stairs, balconies, the roof and the site (driveway, paths, patio, trees, shrubs, hedges), all with procedural materials. It also has cameras, day and evening lighting presets with interior lights, and floor-plan view layers, and can be rendered from any camera.

Known simplifications: the attic is not modelled (there is a small wedge of air between the top of the eave walls and the roof underside, hidden from outside by the overhang), stairs are solid blocks without balustrades, and doors are shown closed.
