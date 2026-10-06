import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.modification_agent import ModificationAgent
from app.api.routes.designs import get_modification_factory
from app.core.errors import AppError
from app.main import create_app
from app.projects.model import ProjectData
from app.projects.repository import JsonProjectRepository
from tests.fake_claude import FakeClaudeClient, reply
from tests.project_fixtures import project_data

JOB, RENDER = "a" * 32, "b" * 32


@pytest.fixture
def repo(tmp_path: Path) -> JsonProjectRepository:
    return JsonProjectRepository(tmp_path / "projects", tmp_path / "jobs")


@pytest.fixture
def api(make_settings, tmp_path: Path) -> TestClient:
    return TestClient(create_app(make_settings(projects_dir=tmp_path / "projects", jobs_dir=tmp_path / "jobs")))


def data(**changes) -> ProjectData:
    return ProjectData.model_validate(project_data(**changes))


# ----------------------------------------------------------------------------- repository

def test_create_get_list_update_delete(repo: JsonProjectRepository) -> None:
    created = repo.create(data())
    assert created.version == 1 and repo.get(created.id).name == "Family house"
    updated = repo.update(created.id, data(name="Family house v2"), expected_version=1)
    assert updated.version == 2 and updated.created_at == created.created_at and updated.updated_at >= created.updated_at
    assert [p.name for p in repo.list()] == ["Family house v2"]
    repo.delete(created.id)
    assert repo.list() == []
    with pytest.raises(AppError) as caught:
        repo.get(created.id)
    assert caught.value.code == "project_not_found"


def test_saving_over_a_newer_version_is_refused(repo: JsonProjectRepository) -> None:
    project = repo.create(data())
    repo.update(project.id, data(name="Saved in another tab"), expected_version=1)
    with pytest.raises(AppError) as caught:
        repo.update(project.id, data(name="Stale"), expected_version=1)
    assert caught.value.code == "project_changed" and caught.value.details["current_version"] == 2
    assert repo.get(project.id).name == "Saved in another tab"


def test_writes_are_atomic_and_leave_no_temporary_files(repo: JsonProjectRepository) -> None:
    project = repo.create(data())
    repo.update(project.id, data(), expected_version=1)
    files = sorted(p.name for p in repo.root.iterdir())
    assert files == [f"{project.id}.json"]


def test_a_damaged_file_does_not_hide_the_others(repo: JsonProjectRepository) -> None:
    good = repo.create(data())
    (repo.root / ("c" * 32 + ".json")).write_text("{ not json")
    assert [p.id for p in repo.list()] == [good.id]
    with pytest.raises(AppError) as caught:
        repo.get("c" * 32)
    assert caught.value.code == "project_unreadable"


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "ABCDEF" * 6, "x", "a" * 33])
def test_unsafe_ids_never_reach_the_filesystem(repo: JsonProjectRepository, bad_id: str) -> None:
    with pytest.raises(AppError) as caught:
        repo.get(bad_id)
    assert caught.value.code == "project_not_found"


def test_paths_and_urls_are_derived_by_the_server(repo: JsonProjectRepository, tmp_path: Path) -> None:
    (tmp_path / "jobs" / JOB / "renders").mkdir(parents=True)
    (tmp_path / "jobs" / JOB / "building.blend").write_bytes(b"blend")
    (tmp_path / "jobs" / JOB / "renders" / f"{RENDER}.png").write_bytes(b"png")
    project = repo.create(data(
        build={"job_id": JOB, "blender_version": "5.2.2 LTS", "object_count": 140, "cameras": [{"name": "Camera_Exterior_Front", "role": "exterior_front"}]},
        renders=[{"render_id": RENDER, "job_id": JOB, "camera": "Camera_Exterior_Front", "preset": "day", "quality": "preview",
                  "engine": "cycles", "width": 640, "height": 360}],
    ))
    assert project.build.blend_url == f"/api/designs/jobs/{JOB}/building.blend" and project.build.available
    assert project.build.blend_path.endswith(f"jobs/{JOB}/building.blend")
    assert project.renders[0].image_url == f"/api/designs/jobs/{JOB}/renders/{RENDER}.png" and project.renders[0].available
    reopened = repo.get(project.id)  # stored projects carry derived fields; reopening must recompute them
    assert reopened.build.available and reopened.renders[0].available and reopened.build.object_count == 140


def test_files_cleaned_up_after_saving_are_reported_missing(repo: JsonProjectRepository, tmp_path: Path) -> None:
    (tmp_path / "jobs" / JOB).mkdir(parents=True)
    blend = tmp_path / "jobs" / JOB / "building.blend"
    blend.write_bytes(b"blend")
    project = repo.create(data(build={"job_id": JOB}))
    blend.unlink()
    assert repo.get(project.id).build.available is False


# ----------------------------------------------------------------------------- API

def test_save_list_open_and_delete(api: TestClient) -> None:
    created = api.post("/api/projects", json=project_data())
    assert created.status_code == 201
    project = created.json()
    assert project["report"]["status"] == "PASS" and project["summary"]["bedrooms"] == 3
    assert [p["name"] for p in project["plans"]] == ["Ground floor", "First floor"]
    listing = api.get("/api/projects").json()
    assert [(p["id"], p["floors"], p["changes"]) for p in listing] == [(project["id"], 2, 0)]
    assert api.get(f"/api/projects/{project['id']}").json()["brief"].startswith("Create a modern")
    assert api.delete(f"/api/projects/{project['id']}").status_code == 204
    assert api.get(f"/api/projects/{project['id']}").status_code == 404


def test_client_cannot_inject_paths_urls_or_a_report(api: TestClient) -> None:
    payload = project_data(build={"job_id": JOB, "blend_path": "/etc/passwd"})
    assert api.post("/api/projects", json=payload).status_code == 422  # unknown field: rejected outright
    payload = project_data()
    payload["report"] = {"status": "PASS"}
    assert api.post("/api/projects", json=payload).status_code == 422


def test_the_stored_report_is_the_servers_own(api: TestClient) -> None:
    payload = project_data()
    next(r for r in payload["specification"]["rooms"] if r["id"] == "wc")["width"] = 6.0  # now overlaps its neighbours
    project = api.post("/api/projects", json=payload).json()
    assert project["report"]["status"] == "ERROR" and any(i["code"] == "room_overlap" for i in project["report"]["issues"])


def test_conflicting_save_is_a_409(api: TestClient) -> None:
    project = api.post("/api/projects", json=project_data()).json()
    assert api.put(f"/api/projects/{project['id']}", json={**project_data(), "version": 1}).status_code == 200
    stale = api.put(f"/api/projects/{project['id']}", json={**project_data(), "version": 1})
    assert stale.status_code == 409 and stale.json()["error"]["current_version"] == 2


def test_save_reopen_modify_save_again(make_settings, tmp_path: Path) -> None:
    """The round trip: a reopened project can be modified and saved again with its history."""
    change = json.dumps({"understood": True, "summary": "Hip roof.", "assumptions": [],
                         "operations": [{"op": "set_roof", "params": [{"key": "type", "value": "hip"}]}]})
    app = create_app(make_settings(projects_dir=tmp_path / "projects", jobs_dir=tmp_path / "jobs", anthropic_api_key="sk-ant-test"))
    app.dependency_overrides[get_modification_factory] = lambda: (lambda: ModificationAgent(FakeClaudeClient([reply(change)])))
    api = TestClient(app)

    saved = api.post("/api/projects", json=project_data()).json()
    reopened = api.get(f"/api/projects/{saved['id']}").json()
    modified = api.post("/api/designs/modify", json={"request": "Change the roof to a hip roof", "intent": reopened["intent"],
                                                     "overrides": reopened["overrides"], "specification": reopened["specification"]}).json()
    assert modified["changes"] == ["Roof: gable 35° slate -> hip 35° slate."]

    again = api.put(f"/api/projects/{saved['id']}", json={
        **project_data(), "version": reopened["version"], "intent": modified["intent"], "overrides": modified["overrides"],
        "specification": modified["specification"],
        "history": [{"request": "Change the roof to a hip roof", "summary": modified["change_summary"], "changes": modified["changes"], "assumptions": []}],
    }).json()
    assert again["version"] == 2 and again["specification"]["roof"]["type"] == "hip"
    final = api.get(f"/api/projects/{saved['id']}").json()
    assert final["intent"]["roof"]["type"] == "hip" and len(final["history"]) == 1 and final["report"]["error_count"] == 0
