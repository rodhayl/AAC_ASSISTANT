"""
Test suite for user preferences and profile endpoints
"""

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


@pytest.fixture(scope="function")
def prefs_user(test_db_session):
    """Create a test user and return user info tuple (id, username, user_type)"""
    user = User(
        username="prefs_test_user",
        password_hash=get_password_hash("TestPassword123"),
        display_name="Prefs Test User",
        user_type="student",
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return (user.id, user.username, user.user_type)


class TestUserPreferences:
    """Test user preferences endpoints"""

    def test_get_preferences_default(self, prefs_user):
        """Test getting default preferences for new user"""
        user_id, username, user_type = prefs_user
        response = client.get(
            "/api/auth/preferences",
            headers=create_test_headers(user_id, username, user_type),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tts_voice"] == "default"
        assert data["notifications_enabled"] is True
        assert data["dark_mode"] is False

    def test_update_preferences(self, prefs_user):
        """Test updating user preferences"""
        user_id, username, user_type = prefs_user
        response = client.put(
            "/api/auth/preferences",
            headers=create_test_headers(user_id, username, user_type),
            json={
                "tts_voice": "female",
                "notifications_enabled": False,
                "dark_mode": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tts_voice"] == "female"
        assert data["notifications_enabled"] is False
        assert data["dark_mode"] is True

    def test_update_partial_preferences(self, prefs_user):
        """Test updating only some preferences"""
        user_id, username, user_type = prefs_user
        headers = create_test_headers(user_id, username, user_type)

        # First set all preferences
        client.put(
            "/api/auth/preferences",
            headers=headers,
            json={
                "tts_voice": "male",
                "notifications_enabled": True,
                "dark_mode": False,
            },
        )

        # Update only dark_mode
        response = client.put(
            "/api/auth/preferences", headers=headers, json={"dark_mode": True}
        )
        assert response.status_code == 200

        # Verify other settings unchanged
        get_response = client.get("/api/auth/preferences", headers=headers)
        data = get_response.json()
        assert data["tts_voice"] == "male"
        assert data["notifications_enabled"] is True
        assert data["dark_mode"] is True

    def test_preferences_no_auth(self):
        """Test that preferences require authentication"""
        response = client.get("/api/auth/preferences")
        assert response.status_code == 401

        response = client.put("/api/auth/preferences", json={"tts_voice": "female"})
        assert response.status_code == 401


class TestUserProfile:
    """Test user profile endpoints"""

    def test_update_display_name(self, prefs_user):
        """Test updating display name"""
        user_id, username, user_type = prefs_user
        response = client.put(
            "/api/auth/profile",
            headers=create_test_headers(user_id, username, user_type),
            json={"display_name": "New Display Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "New Display Name"

    def test_update_email(self, prefs_user):
        """Test updating email"""
        user_id, username, user_type = prefs_user
        response = client.put(
            "/api/auth/profile",
            headers=create_test_headers(user_id, username, user_type),
            json={"email": "newemail@test.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newemail@test.com"

    def test_update_profile_both_fields(self, prefs_user):
        """Test updating both display name and email"""
        user_id, username, user_type = prefs_user
        response = client.put(
            "/api/auth/profile",
            headers=create_test_headers(user_id, username, user_type),
            json={"display_name": "Updated Name", "email": "updated@test.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"
        assert data["email"] == "updated@test.com"

    def test_profile_no_auth(self):
        """Test that profile update requires authentication"""
        response = client.put("/api/auth/profile", json={"display_name": "Hacker"})
        assert response.status_code == 401

    def test_duplicate_email_rejected(self, test_db_session, prefs_user):
        """Test that duplicate email is rejected"""
        user_id, username, user_type = prefs_user

        # Create another user with an email
        other_user = User(
            username="other_user",
            password_hash=get_password_hash("OtherPassword123"),
            display_name="Other User",
            user_type="student",
            email="taken@test.com",
        )
        test_db_session.add(other_user)
        test_db_session.commit()

        # Try to set prefs_user's email to the taken one
        response = client.put(
            "/api/auth/profile",
            headers=create_test_headers(user_id, username, user_type),
            json={"email": "taken@test.com"},
        )
        assert response.status_code == 400
        assert "already in use" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
