"""Render options and their validation. Standard library only, so it is unit-tested without Blender.

A render request is data: one value from each whitelist below plus the name of a camera that
exists in the built scene. Nothing else is accepted.
"""

import re

PRESETS = ("day", "evening")
ENGINES = ("eevee", "cycles")
RESOLUTIONS = {"1280x720": (1280, 720), "1920x1080": (1920, 1080), "2560x1440": (2560, 1440)}
# quality -> (Cycles samples, EEVEE samples, resolution percentage)
QUALITY = {
    "preview": (16, 16, 50),
    "standard": (64, 64, 100),
    "high": (256, 128, 100),
}
RENDER_ID = re.compile(r"^[0-9a-f]{32}$")


class RenderRequestError(ValueError):
    pass


def validate_render_request(request: object, camera_names: set) -> dict:
    if not isinstance(request, dict):
        raise RenderRequestError("The render request must be an object.")
    checks = {
        "preset": PRESETS, "engine": ENGINES, "quality": tuple(QUALITY), "resolution": tuple(RESOLUTIONS),
    }
    for key, allowed in checks.items():
        if request.get(key) not in allowed:
            raise RenderRequestError(f"{key} must be one of {', '.join(allowed)} (got {request.get(key)!r}).")
    if request.get("camera") not in camera_names:
        raise RenderRequestError(f"There is no camera called {request.get('camera')!r} in this scene.")
    if not isinstance(request.get("render_id"), str) or not RENDER_ID.match(request["render_id"]):
        raise RenderRequestError("The render ID is invalid.")
    extra = set(request) - {"preset", "engine", "quality", "resolution", "camera", "render_id"}
    if extra:
        raise RenderRequestError(f"Unexpected render options: {', '.join(sorted(extra))}.")
    return request
