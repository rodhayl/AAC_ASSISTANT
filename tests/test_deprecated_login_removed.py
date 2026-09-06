"""Deprecated JSON ``POST /auth/login`` is removed (dead + brute-force bypass).

The endpoint duplicated the token route's login logic without the
``conditional_limiter`` rate limit, ``lockout_service`` checks/recording or
``audit_service`` events, and had zero callers (frontend, tests, E2E). It is
unregistered: a request now gets 404/405 instead of an unbounded
credential-guessing surface.
"""

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_deprecated_json_login_endpoint_is_not_registered(setup_test_db):
    """POST /api/auth/login answers 404/405, never a login result."""
    response = client.post(
        "/api/auth/login",
        json={"username": "anyone", "password": "anything"},
    )
    assert response.status_code in (404, 405)


def test_token_endpoint_remains_the_login_route(setup_test_db):
    """The OAuth2 token route (rate-limited, lockout-protected) still exists."""
    response = client.post("/api/auth/token", data={})
    # 401/422 for missing credentials proves the route is registered; it must
    # never fall through to a 404 like the removed endpoint.
    assert response.status_code in (401, 422)
