"""Regression tests for lost username/email insert races.

The pre-check (``ensure_username_email_available``) cannot fully guard a
concurrent INSERT: two requests can both see a free username/email and then
race on the database UNIQUE constraints. Before the fix the losing request
escaped as an unhandled ``IntegrityError`` (HTTP 500); it must now produce
the same conflict response a sequential duplicate gets.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.aac_app.models import User
from src.api.main import app

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("setup_test_db")


def _add_user(test_db_session, *, username: str, email: str | None = None) -> User:
    user = User(
        username=username,
        email=email,
        display_name=username,
        user_type="student",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    return user


def _disable_pre_check(monkeypatch, module: str) -> None:
    """Remove the sequential pre-check so the INSERT itself hits the constraint.

    This is the deterministic stand-in for a request that read a free
    username/email while a concurrent insert was still uncommitted.
    """
    monkeypatch.setattr(f"{module}.ensure_username_email_available", lambda *a, **k: None)


def test_setup_race_returns_409_not_500(
    test_db_session, monkeypatch
):
    """Two concurrent first-run setups with the same username: loser → 409."""
    _add_user(test_db_session, username="race_admin")
    _disable_pre_check(monkeypatch, "src.api.routers.auth")

    response = client.post(
        "/api/auth/setup",
        json={
            "username": "race_admin",
            "display_name": "Race Admin",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]


def test_register_race_returns_409_not_500(
    test_db_session, monkeypatch
):
    """Two concurrent self-registrations with the same username: loser → 409."""
    _add_user(test_db_session, username="race_user")
    _disable_pre_check(monkeypatch, "src.api.routers.auth")

    response = client.post(
        "/api/auth/register",
        json={
            "username": "race_user",
            "display_name": "Race User",
            "password": "RaceUserPass123",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]


def test_admin_create_user_race_returns_409_not_500(
    test_db_session, admin_token, monkeypatch
):
    """Two concurrent admin creations with the same email: loser → 409."""
    _add_user(test_db_session, username="race_email_user", email="race@example.com")
    _disable_pre_check(monkeypatch, "src.api.routers.auth_users")

    response = client.post(
        "/api/auth/admin/create-user",
        json={
            "username": "race_email_other",
            "display_name": "Race Email Other",
            "user_type": "student",
            "password": "RaceEmailPass123",
            "confirm_password": "RaceEmailPass123",
            "email": "race@example.com",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]


def test_update_email_lost_race_returns_409_not_500(
    test_db_session, test_db_engine, admin_token
):
    """A lost update-email race reports the conflict, never a server error.

    The flush is forced to raise the integrity error a concurrent email
    claimant produces (both requests read the address as free, one commit
    wins); without the route's IntegrityError handling this escapes as an
    unhandled exception instead of a 409 response.
    """
    from sqlalchemy.exc import IntegrityError

    from src.api.deps import get_db

    user = _add_user(test_db_session, username="race_update_user")

    def override_get_db():
        session = Session(bind=test_db_engine)
        real_flush = session.flush

        def losing_flush(*args, **kwargs):
            # Auth/token validation also flushes (nothing dirty), so only the
            # route's pending users-row UPDATE may hit the fake constraint.
            if session.dirty:
                raise IntegrityError(
                    "UPDATE users SET email = %(email)s",
                    {},
                    Exception("UNIQUE constraint failed: users.email"),
                )
            return real_flush(*args, **kwargs)

        session.flush = losing_flush
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.put(
            f"/api/auth/users/{user.id}",
            json={"email": "race_update_new@example.com"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]
