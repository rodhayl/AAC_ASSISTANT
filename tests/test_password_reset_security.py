from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import RefreshTokenRecord, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.utils import jwt_utils
from src.aac_app.utils.jwt_utils import (
    create_access_token,
    create_refresh_token,
    refresh_token_expires_at,
)
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)


def _mint_refresh(session, user) -> str:
    """Mint a rotation-backed refresh token for ``user`` (B1 contract)."""
    import secrets

    jti = secrets.token_hex(16)
    session.add(
        RefreshTokenRecord(
            jti=jti,
            family=jti,
            user_id=user.id,
            expires_at=refresh_token_expires_at(),
        )
    )
    session.commit()
    return create_refresh_token(
        {"sub": user.username, "user_id": user.id}, jti=jti
    )


def _legacy_refresh_token(username: str, user_id: int) -> str:
    """A pre-rotation refresh token: valid signature, no ``jti``/``fam`` claim."""
    return jwt_utils._encode_token(
        {"sub": username, "user_id": user_id, "sec_ver": 1},
        token_type="refresh",
        expire=datetime.now(UTC) + timedelta(days=7),
    )


@pytest.mark.usefixtures("setup_test_db")
def test_logout_revokes_existing_access_and_refresh_tokens(test_db_session):
    student = User(
        username="logout_token_target",
        display_name="Logout Token Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    access_token = create_access_token(
        {
            "sub": student.username,
            "user_id": student.id,
            "user_type": student.user_type,
            "sec_ver": student.security_version,
        }
    )
    refresh_token = _mint_refresh(test_db_session, student)
    headers = {"Authorization": f"Bearer {access_token}"}

    response = client.post("/api/auth/logout", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    test_db_session.refresh(student)
    assert student.security_version == 2
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    ).status_code == 401


@pytest.mark.usefixtures("setup_test_db")
def test_logout_with_expired_access_token_still_revokes(test_db_session):
    """Logout must succeed with an expired access token and revoke refresh.

    The access token expires after 2h while the refresh token lives 7 days; a
    user logging out after a long session must not get a 401 that blocks
    revoking the still-valid refresh token.
    """
    student = User(
        username="expired_logout_target",
        display_name="Expired Logout Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    expired_access_token = jwt.encode(
        {
            "sub": student.username,
            "user_id": student.id,
            "user_type": student.user_type,
            "sec_ver": student.security_version,
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iat": datetime.now(UTC) - timedelta(hours=3),
            "iss": "aac-assistant",
        },
        jwt_utils.JWT_SECRET_KEY,
        algorithm=jwt_utils.JWT_ALGORITHM,
    )
    refresh_token = _mint_refresh(test_db_session, student)

    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {expired_access_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    test_db_session.refresh(student)
    assert student.security_version == 2
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    ).status_code == 401


@pytest.mark.usefixtures("setup_test_db")
def test_logout_without_token_returns_ok(test_db_session):
    """Logout without any token still succeeds (client clears local session)."""
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.usefixtures("setup_test_db")
def test_admin_password_reset_rejects_weak_password(test_db_session, admin_user):
    student = User(
        username="reset_target",
        display_name="Reset Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    response = client.post(
        "/api/users/reset-password",
        json={"user_id": student.id, "new_password": "weak"},
        headers=create_test_headers(admin_user.id, admin_user.username, "admin"),
    )

    assert response.status_code == 400
    assert "password" in response.json()["detail"].lower()


@pytest.mark.usefixtures("setup_test_db")
def test_admin_cannot_reset_own_password_via_reset_route(
    test_db_session, admin_user
):
    """Self-reset is rejected; admins must use the change-password endpoint
    that verifies the current password (mirrors the self-delete guard)."""
    original_hash = admin_user.password_hash
    original_security_version = admin_user.security_version
    response = client.post(
        "/api/users/reset-password",
        json={"user_id": admin_user.id, "new_password": "NewPass123"},
        headers=create_test_headers(admin_user.id, admin_user.username, "admin"),
    )

    assert response.status_code == 400
    test_db_session.refresh(admin_user)
    assert admin_user.password_hash == original_hash
    assert admin_user.security_version == original_security_version


@pytest.mark.usefixtures("setup_test_db")
def test_admin_password_reset_revokes_existing_access_and_refresh_tokens(
    test_db_session, admin_user
):
    student = User(
        username="reset_token_target",
        display_name="Reset Token Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    access_token = create_access_token(
        {
            "sub": student.username,
            "user_id": student.id,
            "user_type": student.user_type,
            "sec_ver": student.security_version,
        }
    )
    legacy_access_token = create_access_token(
        {"sub": student.username, "user_id": student.id, "user_type": student.user_type}
    )
    legacy_refresh_token = _legacy_refresh_token(student.username, student.id)
    refresh_token = _mint_refresh(test_db_session, student)
    admin_headers = create_test_headers(admin_user.id, admin_user.username, "admin")

    response = client.post(
        "/api/users/reset-password",
        json={"user_id": student.id, "new_password": "NewPass123"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    test_db_session.refresh(student)
    assert student.security_version == 2

    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    ).status_code == 401
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {legacy_access_token}"}
    ).status_code == 401
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    ).status_code == 401
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": legacy_refresh_token}
    ).status_code == 401


@pytest.mark.usefixtures("setup_test_db")
def test_authenticated_password_change_revokes_the_current_access_token(
    test_db_session,
):
    student = User(
        username="change_token_target",
        display_name="Change Token Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    access_token = create_access_token(
        {
            "sub": student.username,
            "user_id": student.id,
            "user_type": student.user_type,
            "sec_ver": student.security_version,
        }
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.post(
        "/api/auth/change-password",
        json={
            "username": student.username,
            "current_password": "OldPass123",
            "new_password": "NewPass123",
            "confirm_password": "NewPass123",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


@pytest.mark.usefixtures("setup_test_db")
def test_legacy_access_token_without_security_version_remains_compatible_before_credential_change(
    test_db_session,
):
    student = User(
        username="legacy_token_target",
        display_name="Legacy Token Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    # Legacy tokens (no sec_ver claim) remain valid while no credential
    # change has occurred; after a change, only their iat is compared.
    legacy_token = create_access_token(
        {"sub": student.username, "user_id": student.id, "user_type": student.user_type}
    )
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {legacy_token}"}
    ).status_code == 200


@pytest.mark.usefixtures("setup_test_db")
def test_legacy_token_issued_same_second_as_credential_change_is_revoked(
    test_db_session,
):
    """A legacy token issued in the same second as the credential change is
    revoked when the change carries a sub-second timestamp.

    Legacy tokens carry no ``sec_ver`` claim, so validation compares the
    token's ``iat`` (whole-second granularity) against
    ``credentials_changed_at`` (microsecond precision). A change recorded at
    ``T.500000`` within the same second ``T`` as the token's truncated ``iat``
    is strictly later, so the token must not survive the change.
    """
    student = User(
        username="same_second_legacy_target",
        display_name="Same Second Legacy Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    # Anchor both timestamps to the current second (floored) so the token is
    # not expired and the comparison is deterministic in any timezone.
    change_second = datetime.now(UTC).replace(microsecond=0)
    student.credentials_changed_at = change_second.replace(
        tzinfo=None, microsecond=500_000
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    def encode_legacy_token(extra_claims: dict) -> str:
        return jwt.encode(
            {
                "sub": student.username,
                "user_id": student.id,
                "user_type": student.user_type,
                # Same second as the recorded change, truncated to the second.
                "iat": int(change_second.timestamp()),
                "exp": int(change_second.timestamp()) + 7200,
                "iss": "aac-assistant",
                **extra_claims,
            },
            jwt_utils.JWT_SECRET_KEY,
            algorithm=jwt_utils.JWT_ALGORITHM,
        )

    legacy_access_token = encode_legacy_token({})
    legacy_refresh_token = encode_legacy_token({"type": "refresh"})

    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {legacy_access_token}"},
    ).status_code == 401
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": legacy_refresh_token}
    ).status_code == 401


@pytest.mark.usefixtures("setup_test_db")
def test_legacy_token_issued_on_credential_change_second_boundary_stays_valid(
    test_db_session,
):
    """A legacy token whose truncated ``iat`` equals the credential-change
    second is accepted when the change is recorded exactly on the second
    boundary.

    This pins the comparison semantics: only tokens issued strictly before
    ``credentials_changed_at`` are rejected, and ``iat`` truncation to whole
    seconds makes a boundary-second token compare equal rather than older.
    """
    student = User(
        username="boundary_second_legacy_target",
        display_name="Boundary Second Legacy Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    change_second = datetime.now(UTC).replace(microsecond=0)
    student.credentials_changed_at = change_second.replace(
        tzinfo=None, microsecond=0
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    legacy_access_token = jwt.encode(
        {
            "sub": student.username,
            "user_id": student.id,
            "user_type": student.user_type,
            "iat": int(change_second.timestamp()),
            "exp": int(change_second.timestamp()) + 7200,
            "iss": "aac-assistant",
        },
        jwt_utils.JWT_SECRET_KEY,
        algorithm=jwt_utils.JWT_ALGORITHM,
    )

    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {legacy_access_token}"},
    ).status_code == 200


@pytest.mark.usefixtures("setup_test_db")
def test_admin_reset_unlocks_a_locked_out_account(test_db_session, admin_user):
    """H7: a staff reset must restore access immediately.

    Five failed logins lock the account for 15 minutes. Bumping the password
    without clearing the lockout rows leaves the student answering 403
    "account locked" with a correct, freshly set password — the recovery the
    UI actually offers (a reset) does not recover anything.
    """
    from src.aac_app.services.lockout_service import AccountLockoutService

    student = User(
        username="locked_reset_target",
        display_name="Locked Reset Target",
        user_type="student",
        password_hash=get_password_hash("OldPass123"),
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    for _ in range(AccountLockoutService.MAX_ATTEMPTS):
        AccountLockoutService.record_failed_attempt(
            test_db_session, student.username, "10.0.0.4"
        )
    test_db_session.commit()
    locked, _until = AccountLockoutService.is_locked(
        test_db_session, student.username
    )
    assert locked is True

    # Precondition: the correct old password is refused while locked.
    assert (
        client.post(
            "/api/auth/token",
            data={"username": student.username, "password": "OldPass123"},
        ).status_code
        == 403
    )

    response = client.post(
        "/api/users/reset-password",
        json={"user_id": student.id, "new_password": "NewPass123"},
        headers=create_test_headers(admin_user.id, admin_user.username, "admin"),
    )
    assert response.status_code == 200, response.text

    login = client.post(
        "/api/auth/token",
        data={"username": student.username, "password": "NewPass123"},
    )
    assert login.status_code == 200, login.text


def test_reset_password_route_is_rate_limited():
    """H7: the reset route carries the same 10/hour budget as change-password."""
    from src.api.routers.users import reset_user_password

    assert getattr(reset_user_password, "__rate_limited__", False) is True
