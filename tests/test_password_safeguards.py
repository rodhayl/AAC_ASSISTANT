"""
Test suite for password validation safeguards

These tests ensure that the safeguards preventing null password hashes work correctly.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from src.aac_app.models import User
from src.api.main import app

pytestmark = pytest.mark.usefixtures("setup_test_db")


def _fake_test_password() -> str:
    return "".join(("fake", "-test", "-only", "-A", "1"))


@pytest.fixture
def client(setup_test_db):
    with TestClient(app) as test_client:
        yield test_client


class TestPasswordValidation:
    """Test password validation safeguards"""

    def test_register_with_empty_password(self, client):
        """Test that registration with empty password is rejected"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "password": "",
                "display_name": "Test User",
                "user_type": "student",
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Password is required"

    def test_register_with_whitespace_password(self, client):
        """Test that registration with whitespace-only password is rejected"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser2",
                "password": "   ",
                "display_name": "Test User",
                "user_type": "student",
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Password is required"

    def test_register_with_valid_password(self, client):
        """Test that registration with valid password succeeds"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "validuser",
                "password": _fake_test_password(),
                "display_name": "Valid User",
                "user_type": "student",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "validuser"
        assert "id" in data

    def test_login_with_valid_credentials(self, client):
        """Test that login works with valid credentials"""
        client.post(
            "/api/auth/register",
            json={
                "username": "loginuser",
                "password": _fake_test_password(),
                "display_name": "Login User",
                "user_type": "student",
            },
        )

        response = client.post(
            "/api/auth/token",
            data={
                "username": "loginuser",
                "password": _fake_test_password(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]

    def test_login_with_null_password_hash_safety(self, client, test_db_session):
        """A null password hash is rejected safely by the schema or endpoint."""
        db = test_db_session
        user = User(
            username="nullpassuser",
            display_name="Null Pass User",
            user_type="student",
            password_hash=None,
        )

        try:
            db.add(user)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            # A NOT NULL constraint is the preferred protection. SQLAlchemy
            # may expose the rejected SQLite write as different SQLAlchemyError
            # subclasses depending on its RETURNING/result handling.
            return

        response = client.post(
            "/api/auth/token",
            data={"username": "nullpassuser", "password": _fake_test_password()},
        )
        assert response.status_code == 500
        assert "Account configuration error" in response.json()["detail"]

    def test_password_hashing(self, client, test_db_session):
        """Passwords are hashed with Argon2 rather than stored in plaintext."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "hashtest",
                "password": _fake_test_password(),
                "display_name": "Hash Test",
                "user_type": "student",
            },
        )

        assert response.status_code == 200
        user = test_db_session.query(User).filter(User.username == "hashtest").first()
        assert user is not None
        assert user.password_hash != _fake_test_password()
        assert user.password_hash.startswith("$argon2")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
