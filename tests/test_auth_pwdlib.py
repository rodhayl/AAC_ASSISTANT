import bcrypt
import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import User
from src.aac_app.services.auth_service import get_password_hash, verify_password
from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

def _fake_test_password() -> str:
    return "".join(("fake", "-test", "-only", "-A", "1"))


def _fake_wrong_password() -> str:
    return "".join(("fake", "-wrong", "-only", "-B", "2"))


def test_new_password_hashes_use_argon2():
    password_hash = get_password_hash(_fake_test_password())

    assert password_hash.startswith("$argon2")
    assert verify_password(_fake_test_password(), password_hash)


def test_legacy_bcrypt_password_still_verifies():
    password_hash = bcrypt.hashpw(
        _fake_test_password().encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    assert verify_password(_fake_test_password(), password_hash)
    assert not verify_password(_fake_wrong_password(), password_hash)


def test_successful_legacy_login_rehashes_password_to_argon2(
    test_db_session, admin_user
):
    legacy_hash = bcrypt.hashpw(
        _fake_test_password().encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    user = User(
        username="legacy_user",
        email="legacy@example.com",
        display_name="Legacy User",
        user_type="student",
        password_hash=legacy_hash,
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    response = client.post(
        "/api/auth/token",
        data={"username": "legacy_user", "password": _fake_test_password()},
    )

    assert response.status_code == 200
    test_db_session.refresh(user)
    assert user.password_hash.startswith("$argon2")
    assert verify_password(_fake_test_password(), user.password_hash)


def test_admin_unlock_allows_locked_user_to_login(
    test_db_session, admin_user, admin_token
):
    user = User(
        username="locked_user",
        email="locked@example.com",
        display_name="Locked User",
        user_type="student",
        password_hash=get_password_hash(_fake_test_password()),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    failed_login = {"username": "locked_user", "password": _fake_wrong_password()}
    for attempt in range(5):
        response = client.post("/api/auth/token", data=failed_login)
        assert response.status_code == (403 if attempt == 4 else 401)

    response = client.post(
        "/api/auth/admin/unlock-account",
        params={"username": "locked_user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True

    response = client.post(
        "/api/auth/token",
        data={"username": "locked_user", "password": _fake_test_password()},
    )
    assert response.status_code == 200
