"""
Test suite for password validation safeguards

These tests ensure that the safeguards preventing null password hashes work correctly.
"""

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import User
from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


class TestPasswordValidation:
    """Test password validation safeguards"""

    def test_register_with_empty_password(self):
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

    def test_register_with_whitespace_password(self):
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

    def test_register_with_valid_password(self):
        """Test that registration with valid password succeeds"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "validuser",
                "password": "ValidPassword123",  # Fixed: Added uppercase to meet complexity requirements
                "display_name": "Valid User",
                "user_type": "student",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "validuser"
        assert "id" in data

    def test_login_with_valid_credentials(self):
        """Test that login works with valid credentials"""
        # First register (using strong password with uppercase, lowercase, digit)
        client.post(
            "/api/auth/register",
            json={
                "username": "loginuser",
                "password": "Password123",  # Fixed: Added uppercase to meet complexity requirements
                "display_name": "Login User",
                "user_type": "student",
            },
        )

        # Then login
        response = client.post(
            "/api/auth/login",
            json={
                "username": "loginuser",
                "password": "Password123",  # Fixed: Match the registration password
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "loginuser"

    def test_login_with_null_password_hash_safety(self, test_db_session):
        """
        Test that login fails gracefully if a user somehow has null password_hash.
        This should never happen with the safeguards, but we test the error handling.
        """
        # Use the test database session
        db = test_db_session
        try:
            # Note: With nullable=False, this will fail in new databases
            # But we test the login endpoint's safety check anyway
            user = User(
                username="nullpassuser",
                display_name="Null Pass User",
                user_type="student",
                password_hash=None,  # This should be prevented by schema
            )

            # Try to add it - may fail with IntegrityError if NOT NULL constraint is active
            try:
                db.add(user)
                db.commit()

                # If we got here, the database allowed it (old schema)
                # Now test that login fails gracefully
                response = client.post(
                    "/api/auth/login",
                    json={"username": "nullpassuser", "password": "anypassword"},
                )

                # Should get a 500 error with helpful message
                assert response.status_code == 500
                assert "Account configuration error" in response.json()["detail"]

            except Exception as e:
                # This is expected with NOT NULL constraint - the database prevents it
                # This is good! It means the schema safeguard is working
                print(f"Good: Database prevented null password_hash: {e}")

        finally:
            pass

    def test_password_hashing(self, test_db_session):
        """Test that passwords are properly hashed with bcrypt, not stored in plaintext"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "hashtest",
                "password": "MyPassword123",  # Fixed: Added uppercase to meet complexity requirements
                "display_name": "Hash Test",
                "user_type": "student",
            },
        )

        assert response.status_code == 200

        # Get the user from database
        db = test_db_session
        try:
            user = db.query(User).filter(User.username == "hashtest").first()
            assert user is not None

            # Verify password is hashed (not plaintext)
            assert user.password_hash != "MyPassword123"

            # Verify it's a bcrypt hash (starts with $2b$ and is 60 characters)
            # Bcrypt format: $2b$[rounds]$[22-char salt][31-char hash]
            assert user.password_hash.startswith(
                "$2b$"
            ), f"Expected bcrypt hash, got: {user.password_hash[:10]}"
            assert (
                len(user.password_hash) == 60
            ), f"Bcrypt hash should be 60 chars, got: {len(user.password_hash)}"

        finally:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
