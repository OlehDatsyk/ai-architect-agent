from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers import EXAMPLE_IDS


def test_list_examples(client: TestClient) -> None:
    body = client.get("/api/examples").json()
    assert {e["id"] for e in body} == set(EXAMPLE_IDS)
    assert all(e["prompt"].startswith("Create") for e in body)


def test_get_example(client: TestClient) -> None:
    body = client.get("/api/examples/modern-bungalow").json()
    assert body["title"] == "Modern Flat-Roof Bungalow"
    assert body["specification"]["building"]["building_type"] == "bungalow"


def test_unknown_example_is_404(client: TestClient) -> None:
    response = client.get("/api/examples/castle")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "example_not_found"


@pytest.mark.parametrize("bad_id", ["..%2F..%2F.env", "Modern-Bungalow", "bungalow.json", "a--b", "-a"])
def test_unsafe_example_ids_are_rejected(client: TestClient, bad_id: str) -> None:
    response = client.get(f"/api/examples/{bad_id}")
    assert response.status_code in (400, 404)
    assert "specification" not in response.text


def test_missing_examples_directory_gives_empty_list(make_client, tmp_path: Path) -> None:
    client = make_client(examples_dir=tmp_path / "nothing-here")
    assert client.get("/api/examples").json() == []
