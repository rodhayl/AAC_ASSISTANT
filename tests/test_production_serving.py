"""Regression coverage for the single-port production server."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.routing import Mount

from scripts.start_server import is_port_available
from src.api.main import app
from src.api.spa import ImmutableStaticFiles, SPAStaticFiles

client = TestClient(app)

FRONTEND_INDEX = Path("src/frontend/dist/index.html")


def _require_built_frontend() -> None:
    """Skip SPA-serving assertions when the frontend has not been built.

    The CI backend job runs pytest on a fresh checkout that has no
    src/frontend/dist/ (the frontend is built by a parallel job), and the
    dev test runner may run while a production build rewrites dist/. Built-SPA
    serving is exercised end-to-end by the e2e-production and packaging jobs.
    """
    if not FRONTEND_INDEX.is_file():
        pytest.skip("Built frontend not present (run npm run build in src/frontend)")


def test_root_mount_uses_html_static_files_and_serves_deep_links() -> None:
    """The production root serves the built SPA, including client routes."""
    root_mount = next(
        (
            route
            for route in app.routes
            if isinstance(route, Mount) and route.path == ""
        ),
        None,
    )
    if root_mount is None:
        pytest.skip("Frontend mount absent; built frontend not found")

    assert isinstance(root_mount.app, StaticFiles)
    assert isinstance(root_mount.app, SPAStaticFiles)
    assert root_mount.app.html is True

    _require_built_frontend()
    index_html = client.get("/").text
    assert client.get("/login").status_code == 200
    assert client.get("/boards").text == index_html
    assert "<!doctype html>" in index_html.lower()


def test_uploads_mount_uses_immutable_static_files() -> None:
    """The /uploads mount serves UUID-addressed files as immutable."""
    uploads_mount = next(
        (
            route
            for route in app.routes
            if isinstance(route, Mount) and route.path == "/uploads"
        ),
        None,
    )
    assert uploads_mount is not None
    assert isinstance(uploads_mount.app, StaticFiles)
    assert isinstance(uploads_mount.app, ImmutableStaticFiles)


def test_immutable_static_files_sets_cache_control(tmp_path) -> None:
    """Served uploads carry a long-lived immutable Cache-Control header."""
    image = tmp_path / "symbols" / "ab12cd34ef56.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"fake-png-bytes")

    static = ImmutableStaticFiles(directory=tmp_path)
    response = static.file_response(
        image,
        image.stat(),
        {"type": "http", "method": "GET", "path": "/symbols/ab12cd34ef56.png", "headers": [], "query_string": b"", "app": None, "root_path": "", "http_version": "1.1", "scheme": "http", "client": None, "server": None, "state": {}},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_unknown_api_route_returns_json_not_spa_html() -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def test_health_endpoint_is_available_on_the_api_surface() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_static_fallback_returns_json_response_for_api_paths(tmp_path) -> None:
    """API paths under the SPA mount keep JSON 404 semantics.

    Uses an isolated fixture directory so the test does not depend on a
    built frontend (the CI backend job runs on a fresh checkout).
    """
    (tmp_path / "index.html").write_text("<!doctype html>fixture", encoding="utf-8")
    fallback = SPAStaticFiles(directory=tmp_path, html=True)
    response = fallback._not_found_response("api/missing")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404


def test_static_fallback_serves_index_for_spa_routes(tmp_path) -> None:
    """Non-API routes under the SPA mount fall back to index.html."""
    (tmp_path / "index.html").write_text("<!doctype html>fixture", encoding="utf-8")
    fallback = SPAStaticFiles(directory=tmp_path, html=True)
    response = fallback._not_found_response("boards")

    assert isinstance(response, FileResponse)
    assert response.status_code == 200


def test_port_availability_does_not_displace_existing_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        occupied_port = listener.getsockname()[1]

        assert is_port_available("127.0.0.1", occupied_port) is False
        assert listener.fileno() != -1
