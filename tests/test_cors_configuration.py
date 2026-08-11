import pytest
from fastapi.testclient import TestClient

from src.api.main import app, resolve_allowed_origins


def test_non_development_rejects_empty_allowed_origins():
    for environment in ("production", " Production ", "staging", "test"):
        with pytest.raises(RuntimeError, match="explicit origins"):
            resolve_allowed_origins("", environment, 5176)


def test_wildcard_origin_is_rejected():
    with pytest.raises(RuntimeError, match="must not contain"):
        resolve_allowed_origins("*", "development", 5176)


def test_development_allows_empty_origins_with_local_fallback():
    origins = resolve_allowed_origins("", "development", 5176)

    assert origins == [
        "http://localhost:5176",
        "http://127.0.0.1:5176",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_explicit_origins_are_preserved_in_any_environment():
    configured = " https://example.test,https://app.test "
    assert resolve_allowed_origins(configured, "production", 5176) == [
        "https://example.test",
        "https://app.test",
    ]


def test_loaded_app_uses_explicit_configured_origins():
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert cors.kwargs["allow_origins"]
    assert "*" not in cors.kwargs["allow_origins"]


def test_api_responses_are_not_browser_cacheable():
    """API responses must not be served from a browser cache.

    Repeated identical GETs (e.g. a list reload right after a create) must
    return fresh data; Chromium can otherwise serve the first response from
    its in-memory cache and hide newly created records.
    """
    client = TestClient(app)
    api_response = client.get("/api/health")
    assert api_response.headers.get("cache-control") == "no-store"

    # Routes outside the /api prefix keep their default caching behavior.
    non_api_response = client.get("/ready")
    assert non_api_response.headers.get("cache-control") is None
