from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes.designs import get_blender_service, get_render_service
from app.main import create_app
from app.services import render_service
from app.services.blender_service import BlenderService
from tests.helpers import example
from tests.test_blender_service import OK, fake_blender
from tests.test_render_service import make_service


def test_build_lists_the_cameras(make_settings, tmp_path: Path) -> None:
    app = create_app(make_settings(jobs_dir=tmp_path / "jobs"))
    fake = BlenderService(fake_blender(tmp_path, OK), "binary", tmp_path / "jobs", 20)
    app.dependency_overrides[get_blender_service] = lambda: (lambda: fake)
    body = TestClient(app).post("/api/designs/build", json={"specification": example()}).json()
    names = {c["name"] for c in body["cameras"]}
    assert {"Camera_Exterior_Front", "Camera_Interior_LivingRoom", "Camera_FloorPlan_Ground"} <= names


def test_render_and_download(make_settings, tmp_path: Path) -> None:
    render_service._auto_engine.clear()
    service = make_service(tmp_path)
    app = create_app(make_settings(jobs_dir=tmp_path / "jobs"))
    app.dependency_overrides[get_render_service] = lambda: (lambda: service)
    client = TestClient(app)
    response = client.post(f"/api/designs/jobs/{'b' * 32}/renders", json={"camera": "Camera_FloorPlan_Ground", "preset": "evening"})
    assert response.status_code == 200
    body = response.json()
    assert body["completed_stages"] == ["rendering"] and body["engine"] == "eevee"
    image = client.get(body["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"


def test_render_options_are_whitelisted(client: TestClient) -> None:
    for bad in ({"quality": "ultra"}, {"resolution": "8k"}, {"preset": "noon"}, {"engine": "workbench"}, {"output": "/tmp/x"}):
        assert client.post(f"/api/designs/jobs/{'b' * 32}/renders", json=bad).status_code == 422


def test_render_without_blender_configured(client: TestClient) -> None:
    response = client.post(f"/api/designs/jobs/{'b' * 32}/renders", json={})
    assert response.status_code == 503 and response.json()["error"]["code"] == "blender_unavailable"


def test_render_download_rejects_bad_ids(make_settings, tmp_path: Path) -> None:
    client = TestClient(create_app(make_settings(jobs_dir=tmp_path / "jobs")))
    for job, render in (("b" * 32, "..%2F..%2Fscene"), ("b" * 32, "c" * 32), ("..%2Fx", "c" * 32), ("b" * 32, "C" * 32)):
        assert client.get(f"/api/designs/jobs/{job}/renders/{render}.png").status_code == 404
