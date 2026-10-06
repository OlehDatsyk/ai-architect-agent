"""The project brief's definition of done, end to end over HTTP.

Everything is real except Claude, which is scripted: the API, planner, validator, Blender build
and render, modification, rebuild and project storage. Runs when BLENDER_EXECUTABLE is set:

    BLENDER_EXECUTABLE=/path/to/blender python -m pytest tests/e2e -v -s
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.architect_agent import ArchitectAgent
from app.agents.modification_agent import ModificationAgent
from app.api.routes.designs import get_agent_factory, get_modification_factory
from app.main import create_app
from tests.fake_claude import FakeClaudeClient, reply
from tests.intent_fixtures import as_reply_text, british_house_intent

EXECUTABLE = os.environ.get("BLENDER_EXECUTABLE")
pytestmark = [pytest.mark.blender, pytest.mark.skipif(not EXECUTABLE, reason="Set BLENDER_EXECUTABLE to run the end-to-end test.")]

BRIEF = ("Create a modern two-storey British house with three bedrooms, two bathrooms, an open-plan "
         "kitchen/dining room, living room and single garage.")
CHANGE = "Change the exterior to red brick and add another window to the master bedroom."
RED_BRICK_AND_WINDOW = json.dumps({
    "understood": True, "summary": "Red brick walls and a second master bedroom window.", "assumptions": [],
    "operations": [
        {"op": "set_exterior_material", "params": [{"key": "surface", "value": "wall"}, {"key": "material", "value": "brick"},
                                                   {"key": "colour", "value": "#A33A2A"}]},
        {"op": "add_window", "params": [{"key": "room_id", "value": "master_bedroom"}]},
    ],
})


def job_result(tmp: Path, job_id: str) -> dict:
    return json.loads((tmp / "jobs" / job_id / "result.json").read_text())


def test_definition_of_done(make_settings, tmp_path: Path) -> None:
    settings = make_settings(anthropic_api_key="sk-ant-scripted", blender_executable=Path(EXECUTABLE),
                             jobs_dir=tmp_path / "jobs", projects_dir=tmp_path / "projects", render_default_engine="cycles")
    app = create_app(settings)
    claude = FakeClaudeClient([reply(as_reply_text(british_house_intent()))])
    app.dependency_overrides[get_agent_factory] = lambda: (lambda: ArchitectAgent(claude))
    app.dependency_overrides[get_modification_factory] = lambda: (lambda: ModificationAgent(FakeClaudeClient([reply(RED_BRICK_AND_WINDOW)])))
    api = TestClient(app)

    # 1-3: the backend runs and reports Blender as connected.
    assert api.get("/api/health").json()["checks"]["blender"]["status"] == "found"

    # 4-6: the brief is interpreted and a structured BuildingSpecification is produced.
    interpreted = api.post("/api/designs/interpret", json={"prompt": BRIEF}).json()
    assert BRIEF in claude.calls[0]["messages"][0]["content"]
    plan = api.post("/api/designs/plan", json={"intent": interpreted["intent"]}).json()
    spec = plan["specification"]
    assert spec["schema_version"] == "1.0" and len(spec["floors"]) == 2

    # 7-8: validation runs, and the design can be reviewed before anything is built.
    assert plan["report"]["error_count"] == 0
    assert (plan["summary"]["bedrooms"], plan["summary"]["bathrooms"], plan["summary"]["garage"]) == (3, 2, "single")
    assert [p["name"] for p in plan["plans"]] == ["Ground floor", "First floor"]

    # 9-10: generate; Blender builds the house.
    built = api.post("/api/designs/build", json={"specification": spec}).json()
    result = job_result(tmp_path, built["job_id"])
    objects = {o["name"]: o for o in result["objects"]}
    scene = json.loads((tmp_path / "jobs" / built["job_id"] / "scene.json").read_text())

    # 11: walls, floors, doors and windows are built where the scene says, as closed meshes.
    for element in scene["elements"]:
        assert element["name"] in objects, f"{element['name']} was not built"
    kinds = {e["kind"] for e in scene["elements"]}
    assert {"wall", "slab", "room_floor", "door", "window"} <= kinds
    assert all(o["manifold"] and o["volume"] > 0 for o in result["objects"])
    assert len([e for e in scene["elements"] if e["kind"] == "window" and e["tags"].get("part") == "glass"]) == len(spec["windows"])

    # 12: a roof is generated.
    assert any(e["kind"] == "roof" for e in scene["elements"])

    # 13: materials are assigned, procedurally.
    assert result["materials"] and all(m["connected"] and "ShaderNodeTexImage" not in m["node_types"] for m in result["materials"])

    # 14-15: cameras and lighting are created.
    roles = {c["role"] for c in built["cameras"]}
    assert {"exterior_front", "exterior_rear", "exterior_aerial", "floor_plan"} <= roles
    assert any(light["name"].startswith("Light_") for light in scene["lights"])
    assert {"creating_lighting", "creating_cameras"} <= set(built["completed_stages"])

    # 16: Blender saves the project.
    blend = api.get(built["blend_url"])
    assert blend.status_code == 200 and len(blend.content) > 50_000

    # 17: at least one preview render is produced.
    render = api.post(f"/api/designs/jobs/{built['job_id']}/renders", json={}).json()
    image = api.get(render["image_url"])
    assert image.status_code == 200 and image.content[:4] == b"\x89PNG" and render["width"] == 640

    # 18-19: "Change the exterior to red brick and add another window to the master bedroom."
    modified = api.post("/api/designs/modify", json={"request": CHANGE, "intent": interpreted["intent"], "overrides": [],
                                                    "specification": spec}).json()
    assert len(modified["changes"]) == 2, modified["changes"]
    assert "Exterior wall: brick -> brick (#A33A2A)." in modified["changes"]
    assert any(c.startswith("Added a") and "Master Bedroom" in c for c in modified["changes"])
    assert modified["report"]["error_count"] == 0

    # 20: Blender updates the relevant parts: a rebuild in which only those parts differ.
    rebuilt = api.post("/api/designs/build", json={"specification": modified["specification"]}).json()
    after = {o["name"]: o for o in job_result(tmp_path, rebuilt["job_id"])["objects"]}
    added = set(after) - set(objects)
    assert set(objects) <= set(after), "an unchanged object was lost or renamed"
    assert added and all(name.startswith("Window_MasterBedroom") for name in added)
    walls = [o for name, o in after.items() if name.startswith("Wall_GroundFloor_Front")]
    assert walls and all(o["material"] == "MAT_Brick_A33A2A" for o in walls)

    # And the design survives being saved and reopened.
    saved = api.post("/api/projects", json={
        "name": "Definition of done", "brief": BRIEF, "interpretation": interpreted, "intent": modified["intent"],
        "overrides": modified["overrides"], "specification": modified["specification"],
        "history": [{"request": CHANGE, "summary": modified["change_summary"], "changes": modified["changes"]}],
        "build": {"job_id": rebuilt["job_id"], "blender_version": rebuilt["blender_version"], "object_count": rebuilt["object_count"]},
    }).json()
    reopened = api.get(f"/api/projects/{saved['id']}").json()
    assert reopened["build"]["available"] and reopened["report"]["error_count"] == 0 and len(reopened["history"]) == 1
    print(f"\ndefinition of done: {len(objects)} objects built, {len(added)} added by the change, render {render['duration_seconds']:.0f}s")
