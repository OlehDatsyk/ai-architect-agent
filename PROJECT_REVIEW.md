# AI Architect Agent - Project Review

A technical review of the project as it stands at version 1.0.0-rc.1, covering what works, what does not, and what should come next. Supporting detail is in the [Installation Guide](INSTRUCTION.md), [Architecture](ARCHITECTURE.md), [API Documentation](API_DOCUMENTATION.md) and [Security](SECURITY.md).

---

## 1. Executive Summary

AI Architect Agent turns a plain-English building brief into a validated building specification, a reviewed floor plan, a Blender model and rendered images, and lets the user change the design in plain English.

**Maturity:** a complete, well-tested **release candidate for local, single-user use**. Every stage of the pipeline is implemented and exercised by automated tests, including an end-to-end test that drives the whole definition of done over HTTP with real Blender. The one external dependency not covered by automated tests is the live Claude API: those tests exist but run only on request with a key.

**Strengths:** a strict boundary between AI and execution (Claude produces validated data, never code); a deterministic, testable pipeline; careful error handling; extensive tests, including real-Blender tests on two Blender versions.

**Limitations:** rectangular plans only; synchronous long-running requests with no job queue; no authentication or rate limiting; file-based storage that does not scale beyond one process.

## 2. Project Objectives

Early-stage residential design involves translating a client's description into a feasible layout and a visual model, which is slow and requires specialist tools. The project explores whether a language model can handle the *language* part reliably while conventional, verifiable code handles the *geometry* part, producing results a user can inspect, change and render without 3D modelling skills.

It is a concept-design tool. It does not check building regulations, structure or energy performance, and says so in the interface.

## 3. Current Capabilities

| Capability | Status | Notes |
| --- | --- | --- |
| Brief interpretation by Claude | Implemented | Structured outputs, Pydantic validation, one corrective retry |
| Advanced options (constraints) | Implemented | Override the brief: floors, size, rooms, garage, roof, style |
| Room planning | Implemented | Rectangular footprint, central hall, one or two columns of rooms |
| Non-rectangular plans | Not implemented | No L-shapes, courtyards or curved walls |
| Validation and automatic fixes | Implemented | Geometry, access, openings, stairs, roof, site, wall thickness |
| SVG floor plans | Implemented | Returned in responses, not saved to disk |
| Blender model | Implemented | Walls with openings, doors, windows, stairs, balconies, four roof types |
| Procedural materials | Implemented | 19 recipes, no image textures |
| Site and planting | Implemented | Driveway, paths, patio, low-poly trees, shrubs and hedges |
| Cameras and lighting | Implemented | Exterior, interior and floor-plan cameras; day and evening presets |
| Rendering | Implemented | EEVEE or Cycles chosen by measurement; three qualities and resolutions |
| EEVEE on a real GPU | Implemented, not verified | Development machine had no GPU; only the Cycles fallback was exercised |
| Plain-English changes | Implemented | Keeps the existing arrangement; verifies each change's effect |
| Saved projects | Implemented | JSON files, version conflicts, restore in the app |
| System diagnostics | Implemented | Key, verified Claude connection, model, Blender |
| Live generation progress | Partially implemented | Stages update when each request returns; no streaming |
| Furniture, interiors | Not implemented | |
| Structural or regulatory checks | Not implemented | Out of scope by design |
| Authentication, multi-user | Not implemented | |
| Job queue, background processing | Not implemented | |

## 4. Technical Stack Review

| Area | Choice | Assessment |
| --- | --- | --- |
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4 | Modern and appropriate. State lives in custom hooks without a global store, which suits the app's size |
| Backend | FastAPI, Pydantic v2, pydantic-settings | A good fit: typed models double as validation, API schema and documentation |
| AI | Anthropic SDK, structured outputs | Correct choice for reliable machine-readable output; schemas generated from the same Pydantic models the code uses |
| 3D | Blender as a subprocess, scripts in the repository | Isolated and version-independent; tested on Blender 4.2 and 5.2 |
| Validation | Custom rule engine | Domain-specific and well tested; also enforces real wall thickness |
| Storage | JSON files behind a repository interface | Adequate for local use; the interface leaves room for a database |
| Testing | pytest, Vitest, Testing Library, a headless-browser audit tool | Broad and layered (unit, API, real Blender, end-to-end) |
| Configuration | Typed settings with bounds; `.env` | Clean; a test keeps `.env.example` complete |

## 5. Claude Integration Review

**Strengths**

- **One integration point.** `AnthropicStructuredClient` is the only code that calls Anthropic, so request shape, logging and errors are consistent.
- **Structured outputs.** Interpretation and modification use `output_config.format` with schemas generated from Pydantic, and checked at start-up against what structured outputs accept.
- **Validation in depth.** Schema, Pydantic, then domain rules; problems go back to Claude once with specific messages.
- **Error classification.** Nine `CLAUDE_*` codes distinguish key, billing, model, permission, schema, rate-limit and connection problems. Each is logged with status, type and request ID, and explained clearly in the app.
- **Diagnostics.** The **Verify** button and `scripts/check_claude.py` prove that requests and structured output are accepted, rather than only that a key exists.
- **Measured costs.** Attempts and tokens are capped, the system prompt is cached, and the health check is cached.

**Weaknesses**

- **Not verified live in automated testing.** The live tests exist but need a key; the release is therefore a candidate.
- **Model quality is uncontrolled.** The design depends on Claude's judgement within the schema. Tests use scripted replies, so they show the pipeline is correct, not that interpretations are good.
- **The fallback paths are untested against the real API.** The JSON-only and no-cache fallbacks are covered with mocked responses only.
- **Latency.** Interpretation takes tens of seconds in a single blocking request, with no streaming of partial results.

## 6. Blender Integration Review

**Strengths**

- **Data-only boundary.** The backend writes `scene.json`; Blender's scripts validate it and create only what it describes.
- **Robust process handling.** Argument lists, timeouts, captured logs, and a `result.json` contract checked by the backend.
- **Verified geometry.** Tests check for overlaps, clear openings, closed meshes and outward normals, in Python and inside real Blender.
- **Version independence.** Both the application and the `bpy` module work, and both Blender 4.2 and 5.2 are tested.
- **Rendering.** The engine is chosen from Blender's own report of a GPU, after timing-based selection proved unreliable.

**Weaknesses**

- A full rebuild for every change, rather than an incremental update (fast in practice, but not incremental).
- No sandboxing: Blender runs with the backend's permissions.
- Builds and renders block an HTTP request for their full duration.
- Simplified architecture: solid-block stairs without balustrades, closed doors, no attic, no furniture.

## 7. Frontend Review

- **User experience.** A clear three-column layout: brief, work area, system status. The review-before-build step is a good safeguard, and the change panel shows exactly what changed.
- **Advanced options.** Clearly separated from the brief; the count of options set is shown.
- **Progress.** Ten stages, honest about state. They update per request rather than live, which makes the Blender stages appear to finish together.
- **Projects.** Save with version conflict detection, *Saved / Unsaved changes* status, reopen and delete.
- **Diagnostics and errors.** The System panel distinguishes a configured key from a verified connection; error codes become clear messages.
- **Accessibility and responsiveness.** An axe-core audit (WCAG 2 A and AA, including colour contrast) found no violations on desktop and mobile views, and the layout works at phone width.
- **Weakness:** long requests give no intermediate feedback beyond the stage marker.

## 8. Backend Review

- **Structure.** Clear layers: routes, schemas, agents, services, domain models, planner, validation, scene compiler, storage. Routes are thin.
- **Separation of concerns.** Domain logic is free of HTTP and SDK details; the Claude client and the Blender services are the only external boundaries.
- **Asynchronous operation.** Claude calls are `async`. Planning, builds, renders and project operations are synchronous functions run in FastAPI's thread pool, and builds and renders block a worker thread for their duration.
- **Error handling.** One error envelope, stable codes, request IDs, and production-safe messages.
- **Weakness:** process-local state (engine choice, verification cache, project lock) means the backend must run as a single process.

## 9. Code Quality

- **Readability and naming.** Descriptive names and docstrings explaining *why*, not only what.
- **Modularity.** Small focused modules; geometry, planning, validation and compilation are pure functions over Pydantic models.
- **Typing.** Pydantic models throughout the backend; TypeScript with strict type checking in the frontend.
- **Lint.** Ruff runs clean in CI, with a pinned configuration.
- **Duplication.** Low. One notable exception, deliberate: Blender-side validation re-implements checks the backend already makes, because the Blender process must not trust its input.
- **Documentation.** Design documents in `docs/`, plus tests that fail if the README's API table, `.env.example` or documented paths drift from the code.

## 10. Reliability

```
Frontend -> Backend -> Claude API -> validation -> planner -> scene compiler -> Blender -> render
```

| Point | Failure | Handling |
| --- | --- | --- |
| Frontend -> backend | Backend down | System panel shows *Unreachable*; requests time out with a message |
| Claude API | Key, credit, model, rate limit, network | Classified, logged and explained; no retry for account problems |
| Claude output | Invalid design | One corrective retry, then a clear failure listing the problems |
| Planner | Impossible layout | `planning_failed` with the reason |
| Blender | Missing, crashes, times out | Distinct errors; logs kept in the job folder |
| Rendering | Slow engine, blank image | Engine chosen by measurement; blank renders rejected |
| Storage | Concurrent saves, damaged file | Version conflict (409); damaged files skipped in the list |

The weakest point is **long synchronous requests**: a closed browser tab does not stop a running render, and a slow CPU render occupies a worker thread throughout.

## 11. Security Review

Appropriate for local single-user use: the key stays on the backend and out of logs, AI output never becomes code, subprocesses use argument lists, and IDs are validated before filesystem access. The backend has **no authentication and no rate limiting**, and Python dependencies are not locked, so it is not ready for public exposure. See [Security](SECURITY.md) for the threat model and checklist.

## 12. Testing Review

Results on the development machine at this release:

| Suite | Result |
| --- | --- |
| Backend (pytest) | 1,233 passed; Blender, end-to-end and live tests skip unless configured |
| Frontend (Vitest) | 35 passed |
| Real Blender (Blender 4.2.0 and 5.2.2) | All passed |
| End-to-end definition of done (real Blender, scripted Claude) | Passed |
| Accessibility audit (`tools/visual-check`) | No violations |

**Covered well:** models and validation rules; the planner (including 300 random intents); scene geometry; Claude error handling with a mocked transport; agents with scripted replies; API endpoints; project storage and trust boundaries; documentation consistency.

**Gaps:**
- live Claude behaviour (opt-in only);
- EEVEE on a GPU;
- a desktop Blender binary on Windows or macOS (testing used Linux and the `bpy` module);
- concurrent requests;
- browser end-to-end tests of the real UI against a real backend;
- a coverage percentage, which is not measured.

## 13. Performance

| Operation | Observed (development machine, CPU only) | Bottleneck |
| --- | --- | --- |
| Planning | Fractions of a second | Spine-position search |
| Blender build | Under a second inside Blender, a few seconds with start-up | Blender start-up |
| Preview render (Cycles) | 20 to 50 seconds | CPU path tracing; interiors slower |
| High-quality render | Many minutes on CPU | Samples x pixels |
| Interpretation | Not measured live | Claude latency and output length |

Repeated Claude calls are limited by the attempt cap, and cached system prompts reduce the cost of corrections.

## 14. Scalability

| Scenario | Current suitability |
| --- | --- |
| Local single user | **Suitable**: the intended use |
| Several users on one machine or network | **Not suitable**: no authentication, global projects, no rate limiting |
| Cloud deployment | **Not suitable as is**: needs authentication, a queue, sandboxed workers and shared storage |
| Concurrent Blender jobs | **Possible but unbounded**: each request starts its own process, with no limit |

## 15. Strengths

- A clean, defensible AI boundary: Claude interprets language; deterministic code does geometry; Blender receives only data.
- Review before build, and changes that preserve the existing arrangement and verify their effect.
- Deep, layered testing, including real Blender on two versions and an end-to-end test of the definition of done.
- Honest diagnostics and error messages, distinguishing a configured key from a working one.
- Documentation guarded by tests.

## 16. Weaknesses / Limitations

- Rectangular plans with a central hall only.
- Long synchronous requests; no queue, progress stream or cancellation.
- No authentication or rate limiting; projects are global.
- Single-process assumptions (in-memory caches, a thread lock for project saves).
- Generated files are never cleaned up.
- No Python lockfile or dependency scanning.
- Live Claude quality is unmeasured; scripted tests prove plumbing, not design quality.
- Simplified 3D details: no stair balustrades, closed doors, no attic or furniture.

## 17. Recommended Improvements

### High priority

1. Run the live Claude tests and promote the release to 1.0.0.
2. Move builds and renders to background jobs with a status endpoint, concurrency limits and cancellation.
3. Lock Python dependencies and add `pip-audit`, `npm audit` or Dependabot to CI.

### Medium priority

4. Stream progress to the frontend (for example server-sent events) for builds and renders.
5. Add retention and cleanup for `output/jobs/`.
6. Add browser end-to-end tests against a running backend.
7. Measure interpretation quality on a fixed set of briefs.

### Low priority

8. Non-rectangular footprints (L-shapes, wings).
9. Stair balustrades, open doors, an attic, furniture.
10. Incremental Blender updates for small changes.

## 18. Development Roadmap

These are **recommendations, not commitments**.

- **Version 1.x:** live verification and 1.0.0; background jobs with progress; dependency locking and scanning; output cleanup.
- **Version 2.x:** authentication and per-user projects; a database repository; sandboxed Blender workers; rate limiting; deployment behind HTTPS.
- **Long term:** non-rectangular plans and multi-wing buildings; interiors; export to formats used by architects (for example IFC); quality evaluation of AI interpretations.

## 19. Portfolio Value

The project demonstrates:

- **AI integration done carefully:** structured outputs, schema preparation, validation loops, error classification, cost control and diagnostics.
- **Backend engineering:** a layered FastAPI service with typed models, a consistent error contract and configuration.
- **Frontend engineering:** a typed React interface with a clear review workflow, accessibility verified by audit.
- **Algorithmic work:** a deterministic floor planner with a cost-based search, and layout anchoring for changes.
- **3D automation:** procedural geometry, closed roof meshes, procedural materials, fitted cameras and lighting in Blender, driven by data.
- **Software architecture:** clear boundaries between AI, domain logic and external processes.
- **Security awareness:** secret handling, a data-only execution boundary, and validated IDs and paths.
- **Testing discipline:** unit, API, real-Blender and end-to-end tests, plus documentation tests.

## 20. Final Assessment

AI Architect Agent is a coherent, carefully engineered system whose most important design decision, keeping AI on the language side of a validated data boundary, is sound and consistently applied. For its intended use, a single user on their own machine, it is complete and reliable, with unusually thorough testing for a project of this kind.

Its limits are those of a local tool: synchronous long-running work, no authentication, single-process storage and simplified architecture. Running the live Claude tests, moving Blender work to background jobs and locking dependencies would be the right next steps.
