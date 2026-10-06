# Architecture

This document records the main architectural decisions and the reasoning behind them. It is updated as phases land.

## Guiding rule

Claude decides **what** should exist. Deterministic, tested code decides **where** it goes and **how** it is built. The AI never produces geometry coordinates that go unchecked, and never produces code that gets executed.

## Layers

| Layer | Responsibility | Talks to |
| --- | --- | --- |
| React UI | Brief entry, review of the interpreted design, live job status, renders | Backend REST API only |
| FastAPI backend | Owns AI calls, validation, planning, persistence and job orchestration | Claude API, Blender process, storage |
| Agents (Claude) | Turn natural language into structured *design intent* or *ChangeSets* (see [agents.md](agents.md)) | Called by backend services |
| Planner and validator | Pure Python: intent to coordinates (see [planner.md](planner.md)), then rule checks | Nothing external, fully unit-tested |
| Blender library | Versioned `bpy` generators: walls, openings, roof, materials, cameras... | Reads a validated spec JSON |

The `BuildingSpecification` is the contract between layers and carries a `schema_version` so saved projects can be migrated. See [building-specification.md](building-specification.md).

### Why validation is not an agent

Validation is deterministic code in `app/validation/`, not a Claude agent. A validator has to give the same answer every time and be fully testable; it is the safety net that catches mistakes the agents make. Each rule is a pure function from a `ValidationContext` to a list of issues, so adding a rule means adding one function and one test. Pydantic handles shape (types, bounds, unknown keys); the rules handle meaning (overlaps, connections, reachability).

## Coordinate system

Metres throughout. X is building width (left to right seen from the front), Y is depth (front to back), Z is up. The origin is the front-left corner of the building footprint at ground-floor finished floor level. Blender also uses Z-up, so no axis conversion is needed.

## How the backend talks to Claude

- Server-side only, using the Anthropic Python SDK in one module (`app/services/claude_service.py`). The key never leaves the backend, and agents depend on a small protocol so tests can substitute a scripted client.
- Responses use **structured outputs**: the `DesignIntent` JSON schema is sent in `output_config.format`, which constrains Claude's reply to that shape. (Forced tool use was the original plan, but it returns a 400 on current models such as Sonnet 5.5; see [agents.md](agents.md).)
- The reply is validated with Pydantic and then with deterministic intent rules. Errors are sent back once for a complete corrected design; if they persist, the request fails safely with the outstanding issues. Malformed data never reaches the planner or Blender.
- Claude returns **design intent** (rooms, target areas, connections, stairs, style, materials). The planner calculates positions.

## How the backend talks to Blender

*Implemented in Phase 5; see [blender-integration.md](blender-integration.md) for details.*

**Decision: a hybrid, with headless batch execution as the primary path.**

1. **Primary path, headless batch.** For each job the backend compiles the validated spec into a data-only scene description, writes it to a job folder and runs
   `blender --background --python blender/runner.py -- <job.json>`.
   The runner imports this repository's generator modules, builds the scene, saves the `.blend`, renders previews and writes a result manifest. Progress events are written as JSON lines, which the backend relays to the UI, so stages shown are real.
2. **Optional live path, later.** A small Blender add-on can listen on a local socket for a whitelisted set of structured commands (for example `rebuild_room`, `apply_material`) so modifications can update an open scene interactively. It calls the same generator library.
3. **Blender MCP is a development tool, not the production path.** MCP is designed for an AI client to drive Blender directly, and general-purpose Blender MCP servers include an "execute arbitrary Python" tool. That conflicts with this project's rule that no AI-generated code is executed. MCP remains useful during development for inspecting generated scenes and checking geometry.

Why batch first: it is reproducible, testable in CI, needs no open Blender window, isolates crashes from the API process and makes "same spec in, same scene out" easy to verify.

Pure geometry (wall segments, opening positions, stair maths, roof planes, camera framing) lives in plain Python modules with no `bpy` import, so it is unit-tested with pytest. The `bpy` layer stays thin.

## Modification flow

```
current design (intent + overrides + specification)  +  plain-English change
        ▼
Modification Agent (Claude, structured output) ──► ChangeSet: typed operations addressed by ID
        ▼
check each operation ──► layout operations edit the intent; finishing operations join the overrides
        ▼
re-plan keeping the existing arrangement (layout anchor) ──► apply overrides ──► validate
        ▼
verify each operation's effect ──► problems go back to Claude once, then fail safely
        ▼
updated design + a list of what changed ──► rebuild in Blender (unchanged objects keep their names)
```

See [agents.md](agents.md#modification-agent).

## Main technical risks

| Risk | Mitigation |
| --- | --- |
| Floor-plan quality | Spine-and-columns layout chosen by a scored search; route rule stricter than the validator; 300 randomised intents in the test suite; plans reviewed visually during development. |
| Wall topology (shared walls, joins, openings) | Derive walls from room edges with deduplication in pure, tested Python. |
| Blender API changes between versions | Target 4.2 LTS or newer; keep `bpy` calls in a thin layer. |
| Inconsistent Claude output | Structured outputs, Pydantic validation, deterministic intent checks, one controlled correction, safe failure. |
| Slow renders | Background jobs, preview-quality EEVEE by default, Cycles optional. |
| Scope | Strict phase gates: each phase is tested before the next begins. |

## Error and logging conventions

- All errors use the envelope `{"error": {"code", "message", "request_id"}}`. Codes are stable and machine-readable; messages are written for users.
- Every request gets an `X-Request-ID`, which appears in the response header, the error body and the backend log line.

## Data and storage

Saved projects live in `output/projects/<id>.json`, one file each, through `JsonProjectRepository` (`backend/app/projects/repository.py`).

- **What is stored:** the brief and advanced options, Claude's interpretation, the current design intent, overrides and specification, the server's validation report, planner notes, the modification history, and the latest build and renders.
- **Trust:** the client sends only job and render IDs; the server derives every path and URL from them, reports whether each file still exists, and stores its own validation of the specification. Unknown fields (a client-supplied path or report) are rejected.
- **Integrity:** writes go to a temporary file that is renamed into place, so a crash cannot leave half a project. Each save carries the version it was based on; saving over a newer version returns `409 project_changed`.
- **IDs** are random 128-bit hex strings, checked before they touch the filesystem. A damaged file is logged and skipped in the list rather than hiding the other projects.

**Moving to PostgreSQL.** The API depends on the `ProjectRepository` protocol, not on the JSON implementation. A PostgreSQL repository would store the same `Project` model (as JSONB, with the version as a column for the conflict check, `UPDATE ... WHERE id = $1 AND version = $2`) and be swapped in through the `get_repository` dependency; routes, models and tests stay the same.
