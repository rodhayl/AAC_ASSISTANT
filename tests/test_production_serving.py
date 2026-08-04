"""Regression coverage for the single-port production server."""

from __future__ import annotations

import socket
from pathlib import Path

from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.routing import Mount

from scripts.start_server import is_port_available
from src.api.main import app
from src.api.spa import SPAStaticFiles

client = TestClient(app)


def test_root_mount_uses_html_static_files_and_serves_deep_links() -> None:
    """The production root serves the built SPA, including client routes."""
    root_mount = next(
        route for route in app.routes if isinstance(route, Mount) and route.path == ""
    )

    assert isinstance(root_mount.app, StaticFiles)
    assert isinstance(root_mount.app, SPAStaticFiles)
    assert root_mount.app.html is True

    index_html = client.get("/").text
    assert client.get("/login").status_code == 200
    assert client.get("/boards").text == index_html
    assert "<!doctype html>" in index_html.lower()


def test_unknown_api_route_returns_json_not_spa_html() -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def test_health_endpoint_is_available_on_the_api_surface() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_static_fallback_returns_json_response_for_api_paths() -> None:
    fallback = SPAStaticFiles(directory=Path("src/frontend/dist"), html=True)
    response = fallback._not_found_response("api/missing")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404


def test_port_availability_does_not_displace_existing_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        occupied_port = listener.getsockname()[1]

        assert is_port_available("127.0.0.1", occupied_port) is False
        assert listener.fileno() != -1
