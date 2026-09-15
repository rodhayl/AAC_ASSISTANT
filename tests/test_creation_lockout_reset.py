"""H1 (PROMPT_5): new accounts must not inherit stale lockout rows.

Failed logins are recorded for *unknown* usernames (so an attacker can
pre-lock a name before it exists), and ``delete_user`` clears those rows for
exactly that reason. None of the four account-creation paths did — so an
attacker who pre-locked ``admin1`` made first-run setup hand back an account
that was instantly 403-locked on its own first login. Every creation path now
clears the lockout rows inside the same transaction as the insert.
"""

import pytest
from fastapi.testclient import TestClient

from src.aac_app.services.lockout_service import AccountLockoutService
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

PASSWORD = "TestPassword123"


def _prelock(db, username: str) -> None:
    """Record enough failed attempts to lock ``username``."""
    for _ in range(AccountLockoutService.MAX_ATTEMPTS):
        AccountLockoutService.record_failed_attempt(db, username, "10.0.0.9")
    db.commit()
    is_locked, _until = AccountLockoutService.is_locked(db, username)
    assert is_locked, "precondition: the username must start out locked"


def _assert_prerequisite_lock_blocks_login(username: str) -> None:
    """A locked, nonexistent username answers 403 (not 401) — the H1 bug."""
    response = client.post(
        "/api/auth/token", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 403, response.text


def _login_succeeds(username: str) -> None:
    response = client.post(
        "/api/auth/token", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


def test_self_registration_clears_prelockout_rows(test_db_session):
    username = "prelocked_registration"
    _prelock(test_db_session, username)
    _assert_prerequisite_lock_blocks_login(username)

    registered = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": PASSWORD,
            "display_name": "Prelocked Registration",
            "user_type": "student",
        },
    )
    assert registered.status_code in (200, 201), registered.text

    _login_succeeds(username)


def test_admin_create_user_clears_prelockout_rows(test_db_session, admin_user):
    username = "prelocked_admin_create"
    _prelock(test_db_session, username)

    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    created = client.post(
        "/api/auth/admin/create-user",
        headers=headers,
        json={
            "username": username,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "display_name": "Prelocked Admin Create",
            "user_type": "teacher",
        },
    )
    assert created.status_code in (200, 201), created.text

    _login_succeeds(username)


def test_create_student_clears_prelockout_rows(test_db_session, admin_user):
    username = "prelocked_student_create"
    _prelock(test_db_session, username)

    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    created = client.post(
        "/api/users/students",
        headers=headers,
        json={
            "username": username,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "display_name": "Prelocked Student Create",
        },
    )
    assert created.status_code in (200, 201), created.text

    _login_succeeds(username)


def test_initial_setup_clears_prelockout_rows(test_db_session):
    """First run: an attacker pre-locks the documented default admin name."""
    username = "admin1"
    _prelock(test_db_session, username)
    _assert_prerequisite_lock_blocks_login(username)

    # /api/auth/setup is loopback-only by design; drive it from a loopback
    # client so the test exercises the real route rather than the handler.
    # No ``with`` block: entering the context would run the app lifespan,
    # whose seed step creates (and thereby satisfies) the bootstrap admin.
    loopback = TestClient(app, client=("127.0.0.1", 51234))
    response = loopback.post(
        "/api/auth/setup",
        json={
            "username": username,
            "display_name": "Bootstrap Admin",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert response.status_code in (200, 201), response.text

    _login_succeeds(username)
