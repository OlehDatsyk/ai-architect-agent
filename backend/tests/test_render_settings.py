"""The render runner's request checks (standard library only, so testable without Blender)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "blender" / "scripts"))
from render_settings import RenderRequestError, validate_render_request

CAMERAS = {"Camera_Exterior_Front", "Camera_FloorPlan_Ground"}
GOOD = {"render_id": "a" * 32, "camera": "Camera_Exterior_Front", "preset": "day", "quality": "preview",
        "resolution": "1280x720", "engine": "cycles"}


def test_valid_request_passes() -> None:
    assert validate_render_request(dict(GOOD), CAMERAS)["camera"] == "Camera_Exterior_Front"


@pytest.mark.parametrize(("key", "value"), [
    ("preset", "midnight"), ("engine", "workbench"), ("quality", "ultra"), ("resolution", "7680x4320"),
    ("camera", "Camera_Hidden"), ("render_id", "../../etc/passwd_0123456789abcdef0"), ("render_id", "A" * 32),
    ("render_id", 12345),
])
def test_values_outside_the_whitelists_are_rejected(key: str, value: object) -> None:
    with pytest.raises(RenderRequestError):
        validate_render_request({**GOOD, key: value}, CAMERAS)


def test_unexpected_options_are_rejected() -> None:
    with pytest.raises(RenderRequestError, match="output_path"):
        validate_render_request({**GOOD, "output_path": "/tmp/x.png"}, CAMERAS)
