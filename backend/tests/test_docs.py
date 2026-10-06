"""The documentation must not drift from the code. These tests read the docs and check them
against the real routes, settings and files, so a stale claim fails the build."""

import re

import pytest

from app.core.config import REPO_ROOT, Settings
from app.main import create_app

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
ENV_EXAMPLE = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
DOCS = {path: path.read_text(encoding="utf-8") for path in [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]}


def real_routes() -> set[tuple[str, str]]:
    """From the OpenAPI schema, which lists every route whatever FastAPI's internal router layout."""
    schema = create_app(Settings(_env_file=None)).openapi()  # type: ignore[call-arg]
    return {(method.upper(), path) for path, ops in schema["paths"].items() for method in ops}


def _same_shape(path: str) -> str:
    """Parameter names are documentation: /api/projects/{id} and /api/projects/{project_id} match."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def test_route_collection_works() -> None:
    assert len(real_routes()) >= 15  # guards against a collector that silently finds nothing


def documented_routes() -> set[tuple[str, str]]:
    return {(m, p) for m, p in re.findall(r"^\| `(GET|POST|PUT|PATCH|DELETE)` \| `(/api/[^`]+)` \|", README, re.M)}


def test_every_route_is_in_the_readme_api_table() -> None:
    documented = {(m, _same_shape(p)) for m, p in documented_routes()}
    missing = {(m, p) for m, p in real_routes() if (m, _same_shape(p)) not in documented}
    assert not missing, f"routes missing from the README API table: {sorted(missing)}"


def test_every_route_in_the_readme_exists() -> None:
    real = {(m, _same_shape(p)) for m, p in real_routes()}
    stale = {(m, p) for m, p in documented_routes() if (m, _same_shape(p)) not in real}
    assert not stale, f"README lists routes that do not exist: {sorted(stale)}"


def test_every_setting_is_in_env_example() -> None:
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE, re.M))
    internal = {"APP_NAME"}  # fixed product name, not configuration
    expected = {name.upper() for name in Settings.model_fields} - internal
    assert not expected - documented, f"settings missing from .env.example: {sorted(expected - documented)}"


def test_env_example_lists_only_real_settings() -> None:
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE, re.M))
    frontend_only = {"BACKEND_URL"}  # read by vite.config.ts
    unknown = documented - {name.upper() for name in Settings.model_fields} - frontend_only
    assert not unknown, f".env.example documents settings that do not exist: {sorted(unknown)}"


def _mentioned_paths() -> list[tuple[str, str]]:
    found = []
    for doc, text in DOCS.items():
        for path in re.findall(r"`((?:backend|frontend|blender|docs|examples|tools)/[A-Za-z0-9_./-]+)`", text):
            found.append((doc.name, path.rstrip("/.")))
        for path in re.findall(r"\]\((?!https?://|#)([^)#\s]+)", text):  # relative Markdown links
            found.append((doc.name, (doc.parent / path).resolve().relative_to(REPO_ROOT).as_posix()))
    return sorted(set(found))


@pytest.mark.parametrize(("doc", "path"), _mentioned_paths())
def test_paths_mentioned_in_the_docs_exist(doc: str, path: str) -> None:
    if "<" in path or "*" in path:
        pytest.skip("pattern, not a path")
    assert (REPO_ROOT / path).exists(), f"{doc} mentions {path}, which does not exist"
