# AI Architect Agent - Installation and Usage Guide

This guide explains how to install, configure, run and troubleshoot AI Architect Agent. For how the system works internally, see [Architecture](ARCHITECTURE.md); for every endpoint, see [API Documentation](API_DOCUMENTATION.md); for a critical evaluation, see [Project Review](PROJECT_REVIEW.md); for security guidance, see [Security](SECURITY.md).

---

## 1. Introduction

AI Architect Agent turns a plain-English building brief into a 3D building model in Blender. Claude (Anthropic's model) interprets the brief; everything after that is deterministic code that can be tested: a room planner, a validation engine, a scene compiler and a set of Blender scripts.

```
building brief (browser)
  -> backend (FastAPI)
  -> Claude: brief -> structured design intent
  -> room planner: intent -> BuildingSpecification + SVG floor plans
  -> validation
  -> you review and approve
  -> scene compiler: specification -> scene.json (data only)
  -> Blender: geometry, materials, site, lighting, cameras -> building.blend
  -> render -> PNG
```

Nothing is built until you approve the reviewed design, and Claude never writes code that Blender runs: Blender only receives data, which it re-validates (see [Security](SECURITY.md#9-blendersubprocess-security)).

## 2. Main Features

Every feature below is implemented and covered by tests.

| Feature | What it does |
| --- | --- |
| Natural-language briefs | Up to 4,000 characters, with optional advanced options (building type, style, floors, size, bedrooms, bathrooms, garage, roof, detail level) |
| Claude interpretation | Claude returns a structured design intent through Anthropic structured outputs; the result is validated and sent back once for correction if needed |
| Room planning | A deterministic planner lays out rooms, a stair, doors, windows, balconies and the site, and draws SVG floor plans |
| Validation | Rules for geometry, access, openings, stairs, roof, site and real wall thickness, with safe automatic fixes |
| Review before building | Summary, floor plans, requested rooms, planner notes and design checks are shown before anything is built |
| Blender build | Walls with door and window openings, doors, windows, stairs through stairwells, balconies, flat, gable, hip and shed roofs, 19 procedural materials, driveway, paths, patio and planting |
| Cameras and lighting | Exterior, interior and floor-plan cameras fitted to the building; day and evening lighting presets with interior lights |
| Rendering | Any generated camera, day or evening, three quality levels, three resolutions; EEVEE where the machine has a GPU, Cycles otherwise |
| Plain-English changes | "Make the living room 1 metre wider", "change the roof to a hip roof": applied to the existing design without rearranging the rest |
| Saved projects | Save, reopen and delete designs with their change history, build and renders |
| System diagnostics | Backend, Claude key, verified Claude connection, model and Blender status in the System panel |

## 3. Technology Requirements

| Software | Version | Needed for |
| --- | --- | --- |
| Python | 3.11 or newer (`backend/pyproject.toml`); CI uses 3.12 | The backend |
| Node.js and npm | Node.js 22 LTS recommended (CI uses 22). The frontend uses Vite 8, which needs a recent Node.js release | The frontend |
| Blender | 4.2 LTS or newer; tested on 4.2.0 LTS and 5.2.2 LTS | Building and rendering (optional until you build) |
| Anthropic API account | An API key **with API credit** | Interpreting briefs and applying changes |
| Git | Any recent version | Cloning and updating |

**Operating systems.** The project was developed and tested on Linux. The Windows PowerShell commands in this guide have been used on Windows. macOS should work with the Linux commands but has not been tested.

**Blender as a Python module.** Instead of the Blender application, the backend can use a Python environment with the `bpy` package from PyPI (see [Blender setup](#blender-setup)). The automated tests used this route.

## 4. Repository Structure

```
ai-architect-agent/
├── .github/workflows/ci.yml # Lint, backend tests, frontend tests and build, optional Blender job
├── backend/
│   ├── app/
│   │   ├── agents/ # Architect Agent and Modification Agent, with their system prompts
│   │   ├── api/routes/ # HTTP endpoints: health, specifications, examples, designs, projects
│   │   ├── core/ # Settings, logging, middleware, error envelope
│   │   ├── geometry/ # Rectangles, opening placement, stair and roof maths
│   │   ├── models/ # Pydantic models: BuildingSpecification, DesignIntent, rooms, openings...
│   │   ├── modification/ # ChangeSets, applying changes, describing what changed
│   │   ├── planner/ # Deterministic floor planner and SVG floor plans
│   │   ├── projects/ # Saved-project models and JSON storage
│   │   ├── scene/ # Scene compiler: specification -> scene.json
│   │   ├── schemas/ # Request and response models for the API
│   │   ├── services/ # Claude client, Blender build and render services, examples
│   │   └── validation/ # Validation engine, rules and automatic fixes
│   ├── scripts/ # Command-line tools (see below)
│   └── tests/ # pytest suites, including blender/, e2e/ and live/
├── blender/scripts/ # Run inside Blender: scene builder, generators, render runner
├── docs/ # Detailed design documents and images
├── examples/ # Example prompts and matching specifications
├── frontend/src/ # React app: components, hooks, API client, types
├── tools/visual-check/ # Screenshots and an accessibility audit of the running app
├── .env.example # Every setting, documented
├── CHANGELOG.md
├── README.md
├── INSTRUCTION.md # This guide
├── PROJECT_REVIEW.md
├── API_DOCUMENTATION.md
├── ARCHITECTURE.md
└── SECURITY.md
```

Generated files go in `output/` (created on first use and ignored by Git).

Command-line tools in `backend/scripts/`:

| Script | Purpose |
| --- | --- |
| `check_claude.py` | Step-by-step check of the Claude connection: settings, plain request, prompt caching, structured output with a tiny schema and with both of the app's schemas |
| `interpret_brief.py` | Interpret a brief from the command line (`--example`, `--plan DIR`, `--json`) |
| `build_example_specs.py` | Regenerate `examples/specifications/*.json` |

## 5. Installation

### Clone the repository

```bash
git clone <repository-url> ai-architect-agent
cd ai-architect-agent
```

On Windows, keep the project **outside OneDrive** (for example in `C:\dev\ai-architect-agent`): OneDrive tries to sync the tens of thousands of files that `node_modules` and `.venv` contain, which makes installs slow and can lock files.

### Backend setup

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r ..\requirements-dev.txt
```

If activation fails with "running scripts is disabled on this system", run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and activate again.

macOS and Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements-dev.txt
```

`requirements.txt` holds the runtime dependencies (FastAPI, Uvicorn, Pydantic, pydantic-settings, the Anthropic SDK); `requirements-dev.txt` adds pytest, pytest-asyncio, httpx and Ruff.

### Frontend setup

```bash
cd frontend
npm install
```

### Blender setup

The backend finds Blender only through `BLENDER_EXECUTABLE` in `.env`. The System panel reports one of three states: **Executable found**, **Not set up yet** (variable empty) or **Path not found**.

| Blender installed from | Typical `BLENDER_EXECUTABLE` |
| --- | --- |
| blender.org installer (Windows) | `C:\Program Files\Blender Foundation\Blender 4.2\blender.exe` |
| Steam (Windows) | `C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe` |
| macOS application | `/Applications/Blender.app/Contents/MacOS/Blender` |
| Linux package or download | `/usr/bin/blender` or the path to the extracted `blender` |

Write the path without quotes. To check it, run it with `--version`.

`BLENDER_MODE` decides how the backend starts Blender:

| Mode | Command used |
| --- | --- |
| `binary` | `<blender> --background --factory-startup --python <script> -- <arguments>` |
| `python` | `<python-with-bpy> <script> -- <arguments>` |
| `auto` (default) | `python` if the executable's file name starts with "python", otherwise `binary` |

To use the `bpy` module instead of the application, create a separate environment with a matching Python (`bpy` 5.x needs Python 3.13, `bpy` 4.2 needs Python 3.11), `pip install bpy`, and point `BLENDER_EXECUTABLE` at that environment's `python`.

## 6. Environment Configuration

Copy the example file in the project root and edit it:

```powershell
Copy-Item .env.example .env # Windows
```

```bash
cp .env.example .env # macOS and Linux
```

The backend reads `.env` from the project root at start-up only, so **restart the backend after editing it**.

| Variable | Required | Purpose | Example |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | To generate or change designs | Anthropic API key, used only by the backend | `your_api_key_here` |
| `ANTHROPIC_MODEL` | No | Claude model | `claude-sonnet-5-5` (default) |
| `ANTHROPIC_MAX_TOKENS` | No | Largest Claude reply | `8000` (default) |
| `ANTHROPIC_TIMEOUT_SECONDS` | No | Timeout for one Claude request | `120` (default) |
| `ANTHROPIC_MAX_RETRIES` | No | SDK retries on connection errors and overloads | `2` (default) |
| `ANTHROPIC_PROMPT_CACHING` | No | Cache the long system prompts; switched off automatically if Anthropic rejects it | `true` (default) |
| `ARCHITECT_MAX_ATTEMPTS` | No | Claude calls per brief or change: 1 plus corrections | `2` (default) |
| `BLENDER_EXECUTABLE` | To build and render | Path to Blender, or to a Python with `bpy` | see [Blender setup](#blender-setup) |
| `BLENDER_MODE` | No | `auto`, `binary` or `python` | `auto` (default) |
| `BLENDER_TIMEOUT_SECONDS` | No | Longest a build may run | `300` (default) |
| `RENDER_TIMEOUT_SECONDS` | No | Longest a render may run | `900` (default) |
| `RENDER_DEFAULT_ENGINE` | No | `auto` (EEVEE with a GPU, otherwise Cycles), `eevee` or `cycles` | `auto` (default) |
| `EEVEE_PROBE_TIMEOUT_SECONDS` | No | Longest the one-off EEVEE test render may take | `45` (default) |
| `APP_ENV` | No | `development` or `production`; production hides Anthropic's error text from the browser | `development` (default) |
| `LOG_LEVEL` | No | Backend log level | `INFO` (default) |
| `API_HOST`, `API_PORT` | No | Address the backend reports for itself | `127.0.0.1`, `8000` |
| `CORS_ORIGINS` | No | Browser origins allowed to call the API, comma-separated | `http://localhost:5173,http://127.0.0.1:5173` (default) |
| `JOBS_DIR` | No | Where builds and renders are written | `output/jobs` (default) |
| `PROJECTS_DIR` | No | Where saved projects are written | `output/projects` (default) |
| `EXAMPLES_DIR` | No | Example prompts and specifications | `examples` (default) |
| `MAX_REQUEST_BYTES` | No | Largest request body accepted | `1048576` (1 MB, default) |
| `BACKEND_URL` | No (frontend only) | Where the Vite dev server forwards `/api` requests | `http://127.0.0.1:8000` (default) |

`APP_NAME` also exists as a setting, but it is the product name rather than configuration. Empty values for `JOBS_DIR` and `PROJECTS_DIR` fall back to the defaults rather than the current directory.

## 7. Anthropic API Setup

1. **Create a key** at console.anthropic.com under **API Keys**.
2. **Add API credit** under **Settings -> Billing**. API usage is billed separately from a Claude.ai subscription: a Pro or Max plan does not include API credit. Without credit every request fails with `CLAUDE_BILLING_ERROR`.
3. **Put the key in `.env`** in the project root: `ANTHROPIC_API_KEY=your_api_key_here`. The key stays on the backend: it is never sent to the browser, logged or returned by any endpoint.
4. **Choose the model** with `ANTHROPIC_MODEL` if you do not want the default `claude-sonnet-5-5`.
5. **Check the connection**, either:
   - in the app: **Verify** in the System panel (a tiny text request and a tiny structured-output request, cached for 10 minutes), or
   - in a terminal, with the backend's environment active:

     ```bash
     cd backend
     python -m scripts.check_claude
     ```

     It checks the settings, a plain request, prompt caching, structured output with a tiny schema, then with the interpretation and modification schemas, and stops at the first failure with Anthropic's own explanation and what to do.

## 8. Running the Application

Two terminals are needed.

**Terminal 1, backend** (Windows; on macOS and Linux use `source .venv/bin/activate`):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

**Terminal 2, frontend:**

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The Vite development server forwards every `/api` request to the backend (`BACKEND_URL`, default `http://127.0.0.1:8000`), so the browser only ever talks to one address.

**Production build.** `npm run build` type-checks and builds the frontend into `frontend/dist/`, and `npm run preview` serves that build locally. Serving the built frontend from the backend, or any production deployment, is **not currently implemented**: the project is designed for local use (see [Security](SECURITY.md#19-local-deployment-vs-public-deployment)).

## 9. Using AI Architect Agent

1. Start the backend and the frontend, and open http://localhost:5173.
2. Check the **System** panel: *Backend API* connected, *Claude API key* configured, *Blender* found. Click **Verify** under *Claude API*: it should report *Verified*.
3. Type a brief in **Describe the building you want to create**, or click **Example prompt**.
4. Optionally open **Advanced options** to fix the building type, style, number of floors, dimensions, bedrooms, bathrooms, garage, roof or detail level. Options override the brief.
5. Click **Generate design**. Claude interprets the brief, then the planner lays it out (stages 1 to 4).
6. **Review** the result: summary, floor plans for each floor (tabs), *Change this design*, requested rooms, how the plan differs from the brief, and design checks. Nothing has been built yet.
7. Optionally describe a change in **Change this design** and click **Apply change**. The list under *What changed* shows exactly what was altered.
8. Click **Approve and generate**. Blender builds the house (stages 5 to 9) and a preview of the front renders automatically (stage 10).
9. Click **Download the .blend file** to open the model in Blender, or use **Renders** to render any camera in day or evening light at higher quality.
10. Name the design and click **Save project**. It appears under **Projects**, where you can reopen or delete it. **Edit brief** returns to the brief to start a new design.

## 10. Writing Good Building Briefs

The planner places rooms in one or two columns either side of a central hall on a rectangular footprint, so briefs for rectangular houses and small offices work best. Floors from one to three have been tested extensively; the model accepts up to ten.

Good briefs name the rooms and their rough sizes, the number of floors, materials and the roof:

- **Simple house:** "A single-storey modern bungalow with two bedrooms, a bathroom, an open-plan kitchen and living room, white render walls and a flat roof."
- **Family house:** "Create a two-storey contemporary British detached house with three bedrooms, two bathrooms, an open-plan kitchen and dining area, separate living room, downstairs WC, utility room and single garage."
- **Scandinavian house:** "A two-storey Scandinavian house clad in dark timber, with a steep metal roof, four bedrooms, large windows to the garden and an open-plan ground floor."
- **Larger house:** "A large contemporary house with a double garage, home office, open-plan kitchen and dining room, four bedrooms (the master with en-suite, dressing room and a rear balcony) and a hip slate roof."
- **Small office:** "A two-storey office with a reception, an open-plan office for twelve people, two meeting rooms, a kitchen and accessible toilets."

The five matching examples are in `examples/prompts/`. Requests that are not buildings, or not achievable on a rectangular footprint (curved walls, L-shaped plans, courtyards), are either refused or simplified, and the review lists the simplifications.

## 11. Generation Stages

The stage list in the right-hand panel shows real progress. Each stage completes when the HTTP request that performs it returns; stages within one request (for example 5 to 9, all done by one Blender build) complete together.

| # | Stage | Request | Input -> output | Typical errors |
| --- | --- | --- | --- | --- |
| 1 | Understanding request | `POST /api/designs/interpret` | Brief and options -> validated design intent from Claude | `anthropic_key_missing`, `CLAUDE_*` codes, `not_a_building_request`, `design_interpretation_failed` |
| 2 | Creating architectural specification | `POST /api/designs/plan` | Intent -> `BuildingSpecification` | Planning failure (with the reason) |
| 3 | Validating design | same request | Specification -> validation report and safe fixes | `building_validation_failed` |
| 4 | Planning rooms | same request | Room layout and SVG floor plans | as stage 2 |
| 5 | Preparing Blender scene | `POST /api/designs/build` | Specification -> `scene.json`; Blender starts | `blender_unavailable` |
| 6 | Generating geometry | same request | Walls, openings, slabs, stairs, roof, site | `blender_build_failed`, `blender_timeout` |
| 7 | Applying materials | same request | 19 procedural material recipes (created before geometry inside Blender) | as stage 6 |
| 8 | Creating lighting | same request | Sun, sky and interior lights; day and evening presets | as stage 6 |
| 9 | Creating cameras | same request | Exterior, interior and floor-plan cameras | as stage 6 |
| 10 | Rendering | `POST /api/designs/jobs/{job_id}/renders` | Camera and options -> PNG | `render_failed`, `render_timeout`, `unknown_camera` |

Error codes are explained in [API Documentation](API_DOCUMENTATION.md#11-error-responses).

## 12. Output Files

| File | Location | Created by |
| --- | --- | --- |
| `scene.json` | `output/jobs/<job_id>/` | Build: the data sent to Blender |
| `building.blend` | `output/jobs/<job_id>/` | Build: the Blender model (also downloadable) |
| `result.json` | `output/jobs/<job_id>/` | Build: what Blender built, per object and material |
| `progress.jsonl`, `blender.log` | `output/jobs/<job_id>/` | Build: progress and Blender's output |
| `<render_id>.png` | `output/jobs/<job_id>/renders/` | Render: the image |
| `<render_id>.json`, `.request.json`, `.log` | `output/jobs/<job_id>/renders/` | Render: result, request and Blender's output |
| `<project_id>.json` | `output/projects/` | Save project |
| `_engine_probe/` | `output/jobs/` | The one-off engine test used by `auto` rendering |

Floor plans are SVG drawings returned in API responses; they are not written to disk. `output/` is not cleaned up automatically.

## 13. Troubleshooting

| Problem | Cause | Solution |
| --- | --- | --- |
| *Backend API: Unreachable* | The backend is not running, or runs on another port | Start it with `uvicorn app.main:app --reload --port 8000`; check `BACKEND_URL` if you changed the port |
| *Claude API key: Not set* | `ANTHROPIC_API_KEY` empty or `.env` not in the project root | Add the key to `.env` next to `.env.example`, then restart the backend |
| `CLAUDE_BILLING_ERROR` | The Anthropic account has no API credit | Add credit at console.anthropic.com -> Settings -> Billing; a Claude.ai subscription does not include it. Then **Verify** again |
| `CLAUDE_AUTH_ERROR` | The key was rejected (mistyped, revoked) | Create a new key and update `.env`; restart the backend |
| `CLAUDE_MODEL_ERROR` | `ANTHROPIC_MODEL` is not available to the account | Correct the model in `.env`; restart |
| `CLAUDE_PERMISSION_ERROR` | The key's workspace may not use the model | Check the key's workspace permissions in the console |
| `CLAUDE_BAD_REQUEST` (HTTP 400) | Anthropic rejected the request for another reason | In development the app shows Anthropic's reason; run `python -m scripts.check_claude` |
| `CLAUDE_SCHEMA_ERROR` | Anthropic rejected a structured-output schema | The app falls back to JSON-only replies automatically; report the `check_claude` output |
| `CLAUDE_RATE_LIMIT` | Too many requests for the account's limits | Wait a minute and try again |
| `CLAUDE_CONNECTION_ERROR` | No route to api.anthropic.com | Check the connection, VPN or proxy |
| *The brief could not be interpreted* after two attempts | Claude's reply failed validation twice | Rephrase the brief more concretely, or use Advanced options |
| *Blender: Not set up yet* or *Path not found* | `BLENDER_EXECUTABLE` empty or wrong | Set the full path to the executable, without quotes; restart the backend |
| `blender_build_failed` | Blender ran but could not build the scene | Read `output/jobs/<job_id>/blender.log`; check the Blender version is 4.2 or newer |
| `blender_timeout` / `render_timeout` | The build or render took too long | Use Preview quality or a lower resolution; raise `RENDER_TIMEOUT_SECONDS` |
| Renders say *Cycles was used because this machine has no GPU* | No GPU, so EEVEE would run on a software renderer | Expected; set `RENDER_DEFAULT_ENGINE=eevee` only on a machine with a GPU |
| `Activate.ps1` cannot be loaded | PowerShell execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `npm install` or Vite fails to start | Node.js too old | Install Node.js 22 LTS |
| Port 8000 or 5173 already in use | Another backend or frontend is still running | Stop it (Ctrl+C in its terminal) or use another port (`--port`, and `BACKEND_URL` for the frontend) |
| Changes to `.env` have no effect | Settings are read only at start-up | Restart the backend |

## 14. Testing

```bash
# Backend tests and lint (from backend/, environment active)
python -m pytest
ruff check app tests scripts ../blender/scripts

# Frontend tests, type check and build (from frontend/)
npm test
npm run typecheck
npm run build

# Real Blender tests (optional)
BLENDER_EXECUTABLE=/path/to/blender python -m pytest tests/blender -v

# The whole pipeline over HTTP with real Blender and a scripted Claude (optional)
BLENDER_EXECUTABLE=/path/to/blender python -m pytest tests/e2e -v -s

# Live Claude tests (optional; use the API and cost a few cents)
RUN_LIVE_CLAUDE_TESTS=1 python -m pytest -m live -v -s
```

In PowerShell, set variables first: `$env:BLENDER_EXECUTABLE = "C:\path\to\blender.exe"` or `$env:RUN_LIVE_CLAUDE_TESTS = "1"`, then run `python -m pytest ...`.

Screenshots and an accessibility audit of the running app: `cd tools/visual-check && npm install && npm run check`.

## 15. Updating the Project

- **Code:** `git pull`, then reinstall dependencies (`pip install -r ../requirements-dev.txt` and `npm install`) in case they changed, and run the tests.
- **Dependencies:** versions are bounded in `requirements.txt` and `frontend/package.json`. After updating, run the full test suites, and the real-Blender tests if the Blender scripts changed. Check the Anthropic SDK's release notes before crossing a major version.
- **Configuration:** compare your `.env` with `.env.example` after updating: new settings appear there first. Restart the backend after any change.

## 16. Quick Start

```powershell
# once
cp .env.example .env # add ANTHROPIC_API_KEY and BLENDER_EXECUTABLE
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; python -m pip install -r ..\requirements-dev.txt
python -m scripts.check_claude # should end with "Everything works"
cd ..\frontend; npm install

# every time: terminal 1
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000
# every time: terminal 2
cd frontend; npm run dev # then open http://localhost:5173
```
