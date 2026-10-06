# BuildingSpecification

The `BuildingSpecification` is the contract between every part of the system: the Claude agents produce it (through the planner), the validator checks it, the UI shows it for review and the Blender layer builds from it. It is defined with Pydantic in `backend/app/models/`, and its JSON Schema is served at `GET /api/specifications/schema`.

Schema version: **1.0** (`schema_version` field, used for future migrations of saved projects).

## Coordinate system

All values are metres and degrees.

```
            rear  (y = depth)
        ┌──────────────────────┐
        │                      │
  left  │                      │  right
 (x = 0)│                      │ (x = width)
        │                      │
        └──────────────────────┘
 origin ●   front (y = 0)
        X ->        Y ↑ (into the plan)       Z up
```

- Origin: front-left corner of the footprint, at ground-floor finished floor level.
- Rooms, stairs and site areas are positioned by their **front-left (minimum x, y) corner** plus `width` (along X) and `depth` (along Y).
- Areas in front of the building (driveways, paths) have negative `y`.
- Blender is also Z-up, so specifications map onto Blender without axis conversion.

## Structure

| Section | Contents |
| --- | --- |
| `project` | id, name, description, units (`metres`), architectural style, created timestamp |
| `building` | building type, footprint width and depth, floor count, default floor height, foundation height, exterior and interior wall thickness, slab thickness |
| `floors[]` | level (0 = ground), name, elevation, floor-to-floor height |
| `rooms[]` | id, name, type, floor, x, y, width, depth, clear height, wall/floor/ceiling materials |
| `doors[]` | id, type, floor, centre position, rotation, width, height, the room(s) it connects, external flag, material |
| `windows[]` | id, style, room, exterior wall, offset along that wall, width, height, sill height |
| `stairs[]` | from/to floor, footprint corner, width, direction of travel, risers, rise, run |
| `balconies[]` | room, exterior wall, offset, width, projection, railing height, materials |
| `roof` | type (flat, gable, hip, shed), pitch, overhang, material, ridge direction |
| `exterior` | wall, accent, trim, window frame and door materials |
| `environment` | ground, driveway, patio, paths, vegetation, sky, sun direction |

Rooms are stored as one flat list with a `floor` field rather than nested inside floors. That keeps every element addressable by ID, which modification ChangeSets (Phase 11) rely on. `spec.rooms_on_floor(level)` gives the per-floor view.

### Placement conventions

- **Doors** sit centred on a wall centreline. Rotation 0 or 180 means the wall runs along X; 90 or 270 means it runs along Y. External doors leave `connects_room_b` empty. Type `opening` is a doorless opening between open-plan spaces.
- **Windows** name the exterior wall they sit in (`front`, `rear`, `left`, `right`) and give their centre `offset` along that wall in building coordinates (x for front/rear, y for left/right).
- **Stairs** have `risers` rises and `risers - 1` treads, so a flight is `run x (risers − 1)` long on plan.
- **Roof** rise is measured from wall-plate level, excluding overhang. For a shed roof, `ridge_direction` is the axis of the high edge.

### Materials

Materials are identifiers (`brick`, `slate`, `timber_cladding`...) that the Blender layer generates procedurally. Any material can carry a colour override: `{"id": "brick", "colour": "#8c4a36"}`. The shorthand `"brick"` is accepted on input. Rooms without explicit finishes get defaults by type (for example carpet in bedrooms, tile in bathrooms).

### Derived values

`room.area` and the specification's `total_height` are computed. They appear in output but are ignored on input, so a saved specification can be reloaded without the derived numbers contradicting the real dimensions.

## Validation

`POST /api/specifications/validate` returns a report with status **PASS**, **WARNING** or **ERROR**, every issue (errors first), and every automatic fix applied.

Validation runs in three steps:

1. **Schema** (Pydantic): types, required fields, positive and bounded dimensions, ID format, unknown keys. Failures become `schema_invalid` issues with a location such as `rooms[3].width`.
2. **Safe fixes**: small, unambiguous corrections, each listed in the report.
3. **Rules**: one pure function per rule in `backend/app/validation/rules/`.

### Automatic fixes

| Code | When |
| --- | --- |
| `floor_elevation_corrected` | A floor's elevation does not equal the sum of the floor heights below it |
| `room_snapped_to_footprint` | A room overshoots an exterior wall by 5 cm or less |
| `stair_rise_corrected` | Rise x risers does not match floor-to-floor height, and the corrected rise is still within 150-220 mm |
| `roof_ridge_defaulted` | A pitched roof has no ridge direction; it is run along the longer side |
| `window_sill_corrected` | A floor-to-ceiling window has a sill above 0 |

Anything else (moving rooms, resizing them meaningfully, changing roof types) is never done silently; it is reported.

### Rules

| Area | Errors | Warnings |
| --- | --- | --- |
| Identity and floors | duplicate IDs, floor numbering gaps, floor count mismatch | unusually low or tall floors, unrealistic building size |
| Rooms | missing floor, outside footprint, overlapping rooms (with area), narrower than 0.6 m, taller than the floor allows | below typical minimum area, low ceiling, upper room over empty space, unsuitable materials |
| Doors | missing rooms, invalid connections, wrong floor, not on the wall the two rooms share, external door not on an exterior wall, taller than the room, upper-floor external door with no balcony | door type contradicts internal/external flag |
| Windows | missing room, room does not touch that exterior wall, window runs past the room's wall, above the ceiling, overlapping another opening | habitable room with no window |
| Balconies | missing room, not on an exterior wall of the room, wider than the wall | on the ground floor, no door to it |
| Circulation | no ground-floor entrance, rooms unreachable from an entrance, floors with no stair between them, stair to a missing floor or skipping floors, stair outside the building, stair not starting or arriving in a room, stair height mismatch | no front door, stair rising through a non-circulation room, steep or shallow rise, short treads, pitch over 42°, narrow stair, kitchen not connected to a living or dining space |
| Roof | flat roof over 5°, pitched roof outside 5-70°, hip ridge along the shorter side | pitch outside the typical range for its type, overhang over 1.2 m |
| Site | | landscaping overlapping the building, planting close enough to the building to be drawn smaller or left out |
| Wall thickness | stair running into a wall or needing a stairwell through one, door or window running into a neighbouring wall | |

The comfort limits used for stairs and room sizes are typical values for flagging unusual designs. **They are not a compliance check against UK Building Regulations or any other standard.**

## Examples

`examples/specifications/` holds five complete specifications matching the prompts in `examples/prompts/`. They are produced by `backend/scripts/build_example_specs.py` (run `python -m scripts.build_example_specs` from `backend/`). A test fails if the committed JSON drifts from the builder, and every example must validate with status PASS and no fixes.
