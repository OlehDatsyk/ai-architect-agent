# Changelog

## 1.0.0-rc.1: release candidate

All fourteen phases of the project brief are complete. This is a release candidate rather than 1.0.0 for one reason: **the Claude API itself has not yet been exercised by this project.** Every interpretation and modification in the test suites uses scripted Claude responses. The opt-in live tests (`RUN_LIVE_CLAUDE_TESTS=1 python -m pytest -m live`) are ready; once they pass against the real API, this becomes 1.0.0.

### What it does

From a plain-English brief to a rendered 3D house you can change in plain English:

1. **Interpretation.** Claude turns the brief into a structured design intent through structured outputs; the result is validated and sent back once for correction if needed.
2. **Planning.** A deterministic planner lays out rooms, stairs, doors, windows and the site, producing a `BuildingSpecification` and SVG floor plans. Nothing is built until the user approves it.
3. **Validation.** Rules cover geometry, access, openings, stairs, roof, site and real wall thickness, with safe automatic fixes.
4. **Blender.** The specification is compiled to data (never code) and built by a sandboxed Blender process: walls with openings, doors, windows, stairs through stairwells, balconies, four roof types, 19 procedural materials, landscaping, fitted cameras, day and evening lighting and floor-plan view layers.
5. **Rendering.** Whitelisted options (camera, lighting, quality, resolution); EEVEE where the machine has a GPU and Cycles otherwise, chosen by measurement and explained.
6. **Modification.** Claude turns a change request into typed operations; the design is re-planned keeping its existing arrangement, every operation's effect is verified, and the app lists exactly what changed.
7. **Projects.** Designs are saved with their history, build and renders, with atomic writes and version conflict detection.

### Verification status

| Verified | How |
| --- | --- |
| The definition of done, items 1 to 20 | `tests/e2e/test_definition_of_done.py`, over HTTP with real Blender (5.2.2 and 4.2.0 LTS) and a scripted Claude |
| Backend behaviour | pytest suite, including 300 random planner intents |
| Blender geometry, materials, cameras and rendering | Real-Blender suites on Blender 5.2.2 LTS and 4.2.0 LTS, using the `bpy` Python module |
| Interface | Vitest suite; screenshots and a zero-violation axe-core audit in a real headless Chromium (`tools/visual-check`) |
| Documentation | Tests that fail if the README API table, `.env.example` or paths in the docs drift from the code |
| Code quality | Ruff, clean, in CI |

| Not yet verified | Why |
| --- | --- |
| Live Claude interpretation and modification | Needs an Anthropic API key; tests are ready (`-m live`) |
| A desktop Blender application binary | Testing used the `bpy` module, which runs the same scripts |
| EEVEE on a real GPU | The development machine has no GPU; only the Cycles fallback was exercised |
| The GitHub Actions Blender job | Defined but not yet run on GitHub |

### Known limitations

- Layouts are rectangular footprints with a central hall; no L-shaped or courtyard plans.
- Concept designs only: no structural, thermal or building-regulations checks.
- Stairs have no balustrades, doors are shown closed, and the attic is not modelled.
- There is no furniture.
- On a CPU-only machine, high-quality renders can take many minutes.

### Phases

| Phase | Delivered |
| --- | --- |
| 1 | FastAPI backend and React frontend foundations, health checks, error envelope |
| 2 | BuildingSpecification schema, validation engine with automatic fixes, examples |
| 3 | Architect Agent: structured outputs, validation feedback loop |
| 4 | Deterministic floor planner and SVG floor plans |
| 5 | Blender connection: data-only scene compiler and sandboxed runner |
| 6 | Wall openings, doors, windows, stairs, stairwells, balconies, roofs; wall-thickness validation |
| 7 | Procedural materials with world-space texture coordinates |
| 8 | Site surfaces and deterministic low-poly planting |
| 9 | Fitted cameras, floor-plan view layers, day and evening lighting |
| 10 | Rendering with whitelisted options and measured engine choice |
| 11 | Modification Agent: typed ChangeSets, anchored re-planning, verified effects |
| 12 | Saved projects: atomic storage, version conflicts, server-derived paths |
| 13 | Interface polish from a real browser review; validation viewer; accessibility audit |
| 14 | Lint, documentation drift tests, end-to-end definition-of-done test, release |
