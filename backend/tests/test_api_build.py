from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes.designs import get_blender_service
from app.main import create_app
from app.services.blender_service import BlenderService
from tests.helpers import example, find
from tests.test_blender_service import OK, fake_blender


def client_with_fake_blender(make_settings, tmp_path: Path) -> TestClient:
    settings = make_settings(jobs_dir=tmp_path / "jobs")
    app = create_app(settings)
    fake = BlenderService(fake_blender(tmp_path, OK), "binary", tmp_path / "jobs", 20)
    app.dependency_overrides[get_blender_service] = lambda: (lambda: fake)
    return TestClient(app)


def test_build_and_download(make_settings, tmp_path: Path) -> None:
    client = client_with_fake_blender(make_settings, tmp_path)
    response = client.post("/api/designs/build", json={"specification": example()})
    assert response.status_code == 200
    body = response.json()
    assert body["completed_stages"] == ["preparing_scene", "generating_geometry"]
    assert body["object_count"] > 40
    download = client.get(body["blend_url"])
    assert download.status_code == 200 and download.content == b"BLENDER-v502"


def test_invalid_building_never_reaches_blender(make_settings, tmp_path: Path) -> None:
    client = client_with_fake_blender(make_settings, tmp_path)
    data = example()
    find(data["rooms"], "wc")["width"] = 2.2  # overlaps the kitchen
    response = client.post("/api/designs/build", json={"specification": data})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "building_validation_failed"
    assert any(i["code"] == "room_overlap" for i in response.json()["error"]["issues"])
    assert not (tmp_path / "jobs").exists() or not any((tmp_path / "jobs").iterdir())


def test_blender_not_configured(client: TestClient) -> None:
    response = client.post("/api/designs/build", json={"specification": example()})
    assert response.status_code == 503
    assert response.json()["error"]["message"].startswith("Blender connection unavailable")


def test_malformed_specification_is_422_even_without_blender(client: TestClient) -> None:
    assert client.post("/api/designs/build", json={"specification": {"rooms": []}}).status_code == 422


def test_download_rejects_bad_job_ids(make_settings, tmp_path: Path) -> None:
    client = TestClient(create_app(make_settings(jobs_dir=tmp_path / "jobs")))
    for job_id in ("..%2F..%2F.env", "0" * 32, "not-a-job"):
        assert client.get(f"/api/designs/jobs/{job_id}/building.blend").status_code == 404
