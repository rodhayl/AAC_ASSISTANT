"""PROMPT_17 regressions: D1/D2/D3/D5/D7/D8.

- D1: ``UserResponse`` must not inherit the INPUT bounds of ``UserBase``, or
  legacy rows with ``display_name=""`` (legal before D9) 500 every read.
- D2: username reads must strip like the register write path, or padded
  logins miss the account and every padding variant becomes its own lockout
  bucket.
- D3: the admin edit validates the stripped ``display_name`` but must also
  STORE the stripped value, not the raw padded payload.
- D5: emails differing only in local-part case must not create twin accounts
  (writes store lowercase; lookups compare case-insensitively).
- D7: deleting a student with ``content_safety_events`` rows must succeed
  (nullable FK without ON DELETE) and leave no orphans.
- D8: the initial-setup payload bounds username/display_name to their
  columns while keeping the strip -> default-if-empty fallback semantics.
"""

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import ContentSafetyEvent, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

_PASSWORD = "TestPassword123"


def _legacy_user(test_db_session, username, display_name="", email=None):
    user = User(
        username=username,
        email=email,
        display_name=display_name,
        user_type="student",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


# --- D1: legacy display_name="" rows must serialize on reads ---------------


def test_legacy_empty_display_name_reads_via_login_and_get_user(
    test_db_session, admin_user, admin_token
):
    """A pre-D9 row with ``display_name=''`` must not 500 response validation."""
    legacy = _legacy_user(test_db_session, "legacy_empty_name")

    # /token has no response_model; the follow-up /me read (UserResponse) is
    # the serialization that used to blow up with ResponseValidationError.
    login = client.post(
        "/api/auth/token",
        data={"username": "legacy_empty_name", "password": _PASSWORD},
    )
    assert login.status_code == 200, login.text
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["display_name"] == ""

    fetched = client.get(
        f"/api/auth/users/{legacy.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["display_name"] == ""


# --- D2: username reads normalize (strip) like the register writes ---------


def test_login_with_padded_username_succeeds(test_db_session):
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "padded_login_user",
            "display_name": "Padded Login",
            "password": _PASSWORD,
        },
    )
    assert reg.status_code == 200, reg.text

    login = client.post(
        "/api/auth/token",
        data={"username": "  padded_login_user  ", "password": _PASSWORD},
    )
    assert login.status_code == 200, login.text


def test_lockout_is_shared_across_padding_variants(test_db_session):
    """Rotating whitespace padding must NOT create separate lockout buckets."""
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "lockout_rotate_user",
            "display_name": "Lockout Rotate",
            "password": _PASSWORD,
        },
    )
    assert reg.status_code == 200, reg.text

    paddings = [
        "lockout_rotate_user",
        " lockout_rotate_user",
        "lockout_rotate_user ",
        "  lockout_rotate_user ",
        "lockout_rotate_user  ",
    ]
    for attempt, padded in enumerate(paddings):
        response = client.post(
            "/api/auth/token",
            data={"username": padded, "password": "WrongPass123"},
        )
        # The 5th failed attempt (attempt index 4) trips the lock.
        assert response.status_code == (403 if attempt == 4 else 401), (
            attempt,
            response.status_code,
            response.text,
        )

    # Even the CORRECT password is now refused while the account is locked.
    locked = client.post(
        "/api/auth/token",
        data={"username": " lockout_rotate_user ", "password": _PASSWORD},
    )
    assert locked.status_code == 403, locked.text


def test_admin_unlock_with_padded_username_unlocks(test_db_session, admin_token):
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "padded_unlock_user",
            "display_name": "Padded Unlock",
            "password": _PASSWORD,
        },
    )
    assert reg.status_code == 200, reg.text
    for _ in range(5):
        client.post(
            "/api/auth/token",
            data={"username": "padded_unlock_user", "password": "WrongPass123"},
        )

    unlock = client.post(
        "/api/auth/admin/unlock-account",
        params={"username": " padded_unlock_user "},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert unlock.status_code == 200, unlock.text
    assert unlock.json()["ok"] is True

    login = client.post(
        "/api/auth/token",
        data={"username": "padded_unlock_user", "password": _PASSWORD},
    )
    assert login.status_code == 200, login.text


def test_export_with_padded_username_resolves(test_db_session):
    """An export requested for " user " must resolve to the stored "user"
    account instead of 404ing on an exact-match lookup."""
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "padded_export_user",
            "display_name": "Padded Export",
            "password": _PASSWORD,
        },
    )
    assert reg.status_code == 200, reg.text
    login = client.post(
        "/api/auth/token",
        data={"username": "padded_export_user", "password": _PASSWORD},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get(
        "/api/data/export",
        params={"username": "  padded_export_user  "},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    # The signed payload records the canonical stored username.
    assert response.json()["meta"]["username"] == "padded_export_user"


def test_import_with_padded_meta_username_resolves(test_db_session):
    """A signed export whose meta username carries padding must import for the
    stripped account (permission check + lookup normalize like the writes)."""
    from src.api.routers.export_import import compute_checksum

    reg = client.post(
        "/api/auth/register",
        json={
            "username": "padded_import_user",
            "display_name": "Padded Import",
            "password": _PASSWORD,
        },
    )
    assert reg.status_code == 200, reg.text
    login = client.post(
        "/api/auth/token",
        data={"username": "padded_import_user", "password": _PASSWORD},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    base = {
        "meta": {
            "exported_at": "2024-01-01T00:00:00Z",
            "username": "  padded_import_user  ",
        },
        "boards": [],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    payload = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": compute_checksum(base),
            "schema_version": "2",
        },
    }
    imported = client.post("/api/data/import", json=payload, headers=headers)
    assert imported.status_code == 200, imported.text
    assert imported.json()["ok"] is True


# --- D3: admin edit stores the stripped display_name -----------------------


def test_admin_edit_stores_stripped_display_name(test_db_session, admin_token):
    target = _legacy_user(
        test_db_session, "edit_display_target", display_name="Original"
    )

    response = client.put(
        f"/api/auth/users/{target.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"display_name": "  Padded  "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Padded"

    test_db_session.expire_all()
    stored = test_db_session.get(User, target.id)
    assert stored.display_name == "Padded"

    # A whitespace-only value stays rejected.
    blank = client.put(
        f"/api/auth/users/{target.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"display_name": "   "},
    )
    assert blank.status_code == 400, blank.text


# --- D5: emails differ only in local-part case are the same account --------


def test_register_normalizes_email_case_and_rejects_case_variant(
    test_db_session,
):
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "email_case_user",
            "display_name": "Email Case",
            "password": _PASSWORD,
            "email": "MixedCase@Example.COM",
        },
    )
    assert reg.status_code == 200, reg.text
    stored = (
        test_db_session.query(User)
        .filter(User.username == "email_case_user")
        .first()
    )
    assert stored.email == "mixedcase@example.com"

    duplicate = client.post(
        "/api/auth/register",
        json={
            "username": "email_case_user_2",
            "display_name": "Email Case 2",
            "password": _PASSWORD,
            "email": "MIXEDCASE@EXAMPLE.com",
        },
    )
    assert duplicate.status_code == 400, duplicate.text


def test_legacy_mixed_case_email_still_matches_lookups(test_db_session):
    """Rows written before lowercase normalization keep logging in and still
    block a case-variant re-registration (compare via SQL lower)."""
    _legacy_user(
        test_db_session,
        "legacy_email_user",
        display_name="Legacy Email",
        email="Old@Case.COM",
    )

    duplicate = client.post(
        "/api/auth/register",
        json={
            "username": "legacy_email_user_2",
            "display_name": "Legacy Email 2",
            "password": _PASSWORD,
            "email": "OLD@case.com",
        },
    )
    assert duplicate.status_code == 400, duplicate.text


def test_update_profile_rejects_case_variant_of_taken_email(
    test_db_session, admin_user
):
    holder = _legacy_user(
        test_db_session, "email_holder_user", display_name="Holder", email="a@x.com"
    )
    other = _legacy_user(
        test_db_session, "email_changer_user", display_name="Changer"
    )

    login = client.post(
        "/api/auth/token",
        data={"username": "email_changer_user", "password": _PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.put("/api/auth/profile", headers=headers, json={"email": "A@X.com"})
    assert response.status_code == 400, response.text
    test_db_session.expire_all()
    assert test_db_session.get(User, other.id).email is None
    assert test_db_session.get(User, holder.id).email == "a@x.com"


# --- D7: delete_user removes content_safety_events -------------------------


def test_delete_user_with_content_safety_events_succeeds_without_orphans(
    test_db_session, admin_user, admin_token
):
    student = _legacy_user(
        test_db_session, "reported_student_delete", display_name="Reported Student"
    )
    event = ContentSafetyEvent(
        user_id=student.id,
        surface="chat",
        direction="input",
        verdict="blocked",
        matched=["term"],
        detail="test event",
    )
    test_db_session.add(event)
    test_db_session.commit()
    student_id = student.id

    response = client.delete(
        f"/api/auth/users/{student_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text

    test_db_session.expire_all()
    assert test_db_session.get(User, student_id) is None
    assert (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == student_id)
        .count()
        == 0
    )


# --- D8: initial-setup payload bounds + fallback defaults ------------------

_SETUP_PASSWORD = "S3tup!Passw0rdZ9"


def test_setup_rejects_overlong_username_and_display_name(test_db_session):
    overlong_name = client.post(
        "/api/auth/setup",
        json={
            "username": "x" * 10_000,
            "display_name": "Administrator",
            "password": _SETUP_PASSWORD,
            "confirm_password": _SETUP_PASSWORD,
        },
    )
    assert overlong_name.status_code == 422, overlong_name.text

    overlong_display = client.post(
        "/api/auth/setup",
        json={
            "username": "admin2",
            "display_name": "y" * 10_000,
            "password": _SETUP_PASSWORD,
            "confirm_password": _SETUP_PASSWORD,
        },
    )
    assert overlong_display.status_code == 422, overlong_display.text

    assert (
        test_db_session.query(User).filter(User.user_type == "admin").count() == 0
    )


def test_setup_whitespace_name_falls_back_to_documented_defaults(test_db_session):
    response = client.post(
        "/api/auth/setup",
        json={
            "username": "     ",
            "display_name": "   ",
            "password": _SETUP_PASSWORD,
            "confirm_password": _SETUP_PASSWORD,
        },
    )
    assert response.status_code == 200, response.text

    admin = (
        test_db_session.query(User).filter(User.user_type == "admin").first()
    )
    assert admin is not None
    assert admin.username == "admin1"
    assert admin.display_name == "Administrator"
