"""H3 (PROMPT_5): refresh tokens rotate and are single-use.

Before this change the refresh token was a 7-day bearer credential with no
server-side state: one stolen copy minted access tokens until it expired or
the password changed. Each exchange now consumes the presented ``jti`` and
mints a successor in the same family; re-presenting a consumed token outside
a short grace window is replayed and revokes the account's sessions through
``security_version``.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.refresh_token import RefreshTokenRecord
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.utils import jwt_utils
from src.aac_app.utils.jwt_utils import decode_refresh_token
from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

PASSWORD = "TestPassword123"


def _login(username: str) -> dict:
    response = client.post(
        "/api/auth/token", data={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _refresh(refresh_token: str):
    return client.post("/api/auth/refresh", json={"refresh_token": refresh_token})


def _legacy_refresh_token(username: str, user_id: int) -> str:
    """A pre-rotation refresh token: valid signature, no ``jti``/``fam`` claim."""
    return jwt_utils._encode_token(
        {"sub": username, "user_id": user_id, "sec_ver": 1},
        token_type="refresh",
        expire=datetime.now(UTC) + timedelta(days=7),
    )


def test_refresh_rotates_the_token(admin_user):
    tokens = _login(admin_user.username)
    original = tokens["refresh_token"]

    rotated = _refresh(original)
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["access_token"]
    assert body["refresh_token"] != original

    # The successor is itself usable for a further rotation.
    again = _refresh(body["refresh_token"])
    assert again.status_code == 200, again.text


def test_old_refresh_token_is_rejected_after_the_grace_window(
    admin_user, test_db_session
):
    tokens = _login(admin_user.username)
    original = tokens["refresh_token"]

    rotated = _refresh(original)
    assert rotated.status_code == 200, rotated.text
    successor = rotated.json()["refresh_token"]

    # Age the consumption past the grace window: this is now a replay.
    test_db_session.rollback()
    record = (
        test_db_session.query(RefreshTokenRecord)
        .filter(RefreshTokenRecord.jti == decode_refresh_token(original)["jti"])
        .one()
    )
    record.consumed_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    test_db_session.commit()

    replay = _refresh(original)
    assert replay.status_code == 401, replay.text

    # Replay revokes the family: the legitimate successor is dead too.
    assert _refresh(successor).status_code == 401


def test_duplicate_in_flight_refresh_inside_the_grace_window_succeeds(admin_user):
    tokens = _login(admin_user.username)
    original = tokens["refresh_token"]

    first = _refresh(original)
    second = _refresh(original)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text


def test_pre_rotation_token_without_jti_still_refreshes(admin_user):
    """Tokens issued before rotation existed must keep working (and rotate)."""
    legacy = _legacy_refresh_token(admin_user.username, admin_user.id)
    assert "jti" not in decode_refresh_token(legacy)

    response = _refresh(legacy)
    assert response.status_code == 200, response.text
    assert decode_refresh_token(response.json()["refresh_token"])["jti"]


def test_legacy_jti_less_token_cannot_mint_twice(admin_user):
    """B1: the one-time legacy exchange invalidates the presented token.

    The first use mints a successor paid for by a security_version bump, so a
    copied pre-rotation token fails its second use instead of minting a fresh
    chain every time until its 7-day expiry.
    """
    legacy = _legacy_refresh_token(admin_user.username, admin_user.id)

    first = _refresh(legacy)
    assert first.status_code == 200, first.text

    second = _refresh(legacy)
    assert second.status_code == 401, second.text


def test_aged_out_ledger_row_is_rotated_exactly_once(
    admin_user, test_db_session, test_db_engine
):
    """B1: an unknown-jti token (row pruned) gets the same one-time grace."""
    tokens = _login(admin_user.username)
    original = tokens["refresh_token"]
    jti = decode_refresh_token(original)["jti"]

    # Simulate ledger aging on its own connection: the row is gone while the
    # token is still valid, which is exactly the "unknown" classification.
    test_db_session.rollback()
    import sqlalchemy

    with test_db_engine.begin() as conn:
        conn.execute(
            sqlalchemy.text("DELETE FROM refresh_token_records WHERE jti = :jti"),
            {"jti": jti},
        )

    first = _refresh(original)
    assert first.status_code == 200, first.text
    assert _refresh(original).status_code == 401


def test_mismatched_family_claim_is_treated_as_replay(admin_user):
    """B3: the family claim is validated, not inherited blindly."""
    import jwt as pyjwt

    forged = pyjwt.encode(
        {
            "sub": admin_user.username,
            "user_id": admin_user.id,
            "sec_ver": 1,
            "jti": "forged-jti-value",
            "fam": "different-family",
            "exp": datetime.now(UTC) + timedelta(days=7),
            "iat": datetime.now(UTC),
            "iss": "aac-assistant",
            "type": "refresh",
        },
        jwt_utils.JWT_SECRET_KEY,
        algorithm=jwt_utils.JWT_ALGORITHM,
    )

    response = _refresh(forged)
    assert response.status_code == 401, response.text

    # Replay handling revokes the account's live sessions too.
    tokens = _login(admin_user.username)
    assert tokens["refresh_token"]  # a fresh login still works


def test_no_family_forgery_path_exists(admin_user):
    """B3: every refresh token now carries a family derived from its jti."""
    tokens = _login(admin_user.username)
    payload = decode_refresh_token(tokens["refresh_token"])
    assert payload["fam"] == payload["jti"]


def test_delete_user_with_refresh_history_succeeds(admin_user, test_db_session):
    """B2: the rotation ledger must not block account deletion with an FK error."""
    from fastapi.testclient import TestClient as _TC  # noqa: F401

    from src.aac_app.models import User as _User

    target = _User(
        username="ledger_delete_target",
        display_name="Ledger Delete Target",
        user_type="student",
        password_hash=get_password_hash(PASSWORD),
        is_active=True,
    )
    test_db_session.add(target)
    test_db_session.commit()

    tokens = _login("ledger_delete_target")
    _refresh(tokens["refresh_token"])
    test_db_session.rollback()
    target_id = target.id
    assert (
        test_db_session.query(RefreshTokenRecord)
        .filter(RefreshTokenRecord.user_id == target_id)
        .count()
        > 0
    )

    from tests.auth_helpers import create_test_headers

    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = client.delete(f"/api/auth/users/{target_id}", headers=headers)
    assert response.status_code == 200, response.text
    test_db_session.rollback()
    assert (
        test_db_session.query(RefreshTokenRecord)
        .filter(RefreshTokenRecord.user_id == target_id)
        .count()
        == 0
    )


def test_logout_clears_the_rotation_ledger(admin_user, test_db_session):
    tokens = _login(admin_user.username)
    test_db_session.rollback()
    assert (
        test_db_session.query(RefreshTokenRecord)
        .filter(RefreshTokenRecord.user_id == admin_user.id)
        .count()
        > 0
    )

    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text

    test_db_session.rollback()
    assert (
        test_db_session.query(RefreshTokenRecord)
        .filter(RefreshTokenRecord.user_id == admin_user.id)
        .count()
        == 0
    )
    # The revoked refresh token can no longer be exchanged either.
    assert _refresh(tokens["refresh_token"]).status_code == 401
