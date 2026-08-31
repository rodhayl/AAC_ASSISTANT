"""
Test suite for user preferences and profile endpoints
"""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import LearningMode, StudentTeacher, User, UserSettings
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from src.api.routers.auth_helpers import build_preferences_response
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


class TestBuildPreferencesResponse:
    """Unit tests for the preferences response mapper."""

    def test_build_preferences_response_uses_defaults_without_settings(self):
        response = build_preferences_response(None)

        assert response.model_dump() == {
            "tts_provider": "kokoro",
            "tts_voice": "default",
            "tts_local_voice": "default",
            "tts_local_speed": 1.0,
            "tts_language": None,
            "ui_language": None,
            "notifications_enabled": True,
            "voice_mode_enabled": True,
            "dark_mode": False,
            "dwell_time": 0,
            "ignore_repeats": 0,
            "high_contrast": False,
            "hover_speak_enabled": False,
            "hover_speak_delay_ms": 1000,
            "default_learning_mode": "practice",
        }

    def test_build_preferences_response_handles_legacy_and_null_values(self):
        settings = SimpleNamespace(
            tts_voice=None,
            notifications_enabled=None,
            dark_mode=None,
            dwell_time=None,
            ignore_repeats=None,
            high_contrast=None,
        )

        response = build_preferences_response(settings)

        assert response.tts_voice == "default"
        assert response.tts_language is None
        assert response.ui_language is None
        assert response.notifications_enabled is True
        assert response.voice_mode_enabled is True
        assert response.dark_mode is False
        assert response.dwell_time == 0
        assert response.ignore_repeats == 0
        assert response.high_contrast is False
        # Missing on legacy rows: falls back to the neutral speed.
        assert response.tts_local_speed == 1.0

    def test_build_preferences_response_clamps_out_of_range_speed(self):
        settings = SimpleNamespace(tts_local_speed=9.0)

        assert build_preferences_response(settings).tts_local_speed == 2.0

        settings = SimpleNamespace(tts_local_speed="fast")

        assert build_preferences_response(settings).tts_local_speed == 1.0

    def test_build_preferences_response_clamps_out_of_range_hover_delay(self):
        settings = SimpleNamespace(hover_speak_delay_ms=99999)

        assert build_preferences_response(settings).hover_speak_delay_ms == 5000

        settings = SimpleNamespace(hover_speak_delay_ms="slow")

        assert build_preferences_response(settings).hover_speak_delay_ms == 1000

    def test_build_preferences_response_maps_populated_settings(self):
        settings = SimpleNamespace(
            tts_provider="browser",
            tts_voice="female",
            tts_local_voice="ef_dora",
            tts_local_speed=1.25,
            tts_language="es",
            ui_language="es-ES",
            notifications_enabled=False,
            voice_mode_enabled=False,
            dark_mode=True,
            dwell_time=250,
            ignore_repeats=3,
            high_contrast=True,
            hover_speak_enabled=True,
            hover_speak_delay_ms=1500,
        )

        response = build_preferences_response(settings)

        assert response.model_dump() == {
            "tts_provider": "browser",
            "tts_voice": "female",
            "tts_local_voice": "ef_dora",
            "tts_local_speed": 1.25,
            "tts_language": "es",
            "ui_language": "es-ES",
            "notifications_enabled": False,
            "voice_mode_enabled": False,
            "dark_mode": True,
            "dwell_time": 250,
            "ignore_repeats": 3,
            "high_contrast": True,
            "hover_speak_enabled": True,
            "hover_speak_delay_ms": 1500,
            "default_learning_mode": "practice",
        }


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
        assert data["tts_provider"] == "kokoro"
        assert data["tts_voice"] == "default"
        assert data["tts_local_voice"] == "default"
        assert data["tts_local_speed"] == 1.0
        assert data["notifications_enabled"] is True
        assert data["dark_mode"] is False
        assert data["default_learning_mode"] == "practice"

    def test_update_preferences(self, prefs_user):
        """Test updating user preferences"""
        user_id, username, user_type = prefs_user
        response = client.put(
            "/api/auth/preferences",
            headers=create_test_headers(user_id, username, user_type),
            json={
                "tts_provider": "browser",
                "tts_voice": "female",
                "tts_local_voice": "ef_dora",
                "tts_local_speed": 1.5,
                "notifications_enabled": False,
                "dark_mode": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tts_provider"] == "browser"
        assert data["tts_voice"] == "female"
        assert data["tts_local_voice"] == "ef_dora"
        assert data["tts_local_speed"] == 1.5
        assert data["notifications_enabled"] is False
        assert data["dark_mode"] is True

    def test_default_learning_mode_roundtrip_and_validation(self, prefs_user, test_db_session):
        """The default mode is persisted only when it is visible to the user."""
        mode = LearningMode(
            name="Quiz",
            key="quiz_preference",
            description="Multiple-choice practice",
            prompt_instruction="Ask quiz questions.",
            is_custom=False,
            created_by=None,
        )
        test_db_session.add(mode)
        test_db_session.commit()

        user_id, username, user_type = prefs_user
        headers = create_test_headers(user_id, username, user_type)
        response = client.put(
            "/api/auth/preferences",
            headers=headers,
            json={"default_learning_mode": mode.key},
        )
        assert response.status_code == 200
        assert response.json()["default_learning_mode"] == mode.key

        stored = (
            test_db_session.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .one()
        )
        assert stored.default_learning_mode == mode.key

        invalid = client.put(
            "/api/auth/preferences",
            headers=headers,
            json={"default_learning_mode": "not_visible"},
        )
        assert invalid.status_code == 400

    def test_update_preferences_rejects_out_of_range_speed(self, prefs_user):
        """Kokoro speed must stay within the range the synthesis endpoint accepts."""
        user_id, username, user_type = prefs_user
        response = client.put(
            "/api/auth/preferences",
            headers=create_test_headers(user_id, username, user_type),
            json={"tts_local_speed": 3.0},
        )
        assert response.status_code == 422
        response = client.put(
            "/api/auth/preferences",
            headers=create_test_headers(user_id, username, user_type),
            json={"tts_local_speed": 0.1},
        )
        assert response.status_code == 422

    def test_concurrent_cross_route_updates_keep_one_settings_row(self, prefs_user, test_db_session):
        """Concurrent preference routes must not duplicate the unique settings row."""
        user_id, username, user_type = prefs_user
        headers = create_test_headers(user_id, username, user_type)

        def update_ui():
            return client.put(
                "/api/settings/ui",
                headers=headers,
                json={"ui_language": "en"},
            )

        def update_preferences():
            return client.put(
                "/api/auth/preferences",
                headers=headers,
                json={"dark_mode": True},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda fn: fn(), (update_ui, update_preferences)))

        assert [response.status_code for response in responses] == [200, 200]
        settings_rows = (
            test_db_session.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .all()
        )
        assert len(settings_rows) == 1
        assert settings_rows[0].ui_language == "en"
        assert settings_rows[0].dark_mode is True

        # Repeat the concurrent first-write scenario to catch intermittent
        # regressions in the route/session boundary.
        for language in ("es-ES", "en", "es-ES"):
            def update_ui_for_language(language=language):
                return client.put(
                    "/api/settings/ui",
                    headers=headers,
                    json={"ui_language": language},
                )

            def update_preferences_for_language(language=language):
                return client.put(
                    "/api/auth/preferences",
                    headers=headers,
                    json={"ui_language": language, "dark_mode": language == "en"},
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(
                    executor.map(
                        lambda fn: fn(),
                        (update_ui_for_language, update_preferences_for_language),
                    )
                )
            assert [response.status_code for response in responses] == [200, 200]

        settings_rows = (
            test_db_session.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .all()
        )
        assert len(settings_rows) == 1

    def test_preferences_reject_unsupported_language_and_out_of_range_timing(self, prefs_user):
        """The API accepts only configured UI languages and the UI timing range."""
        user_id, username, user_type = prefs_user
        headers = create_test_headers(user_id, username, user_type)

        unsupported = client.put(
            "/api/auth/preferences",
            headers=headers,
            json={"ui_language": "fr-FR"},
        )
        assert unsupported.status_code == 400

        too_large = client.put(
            "/api/auth/preferences",
            headers=headers,
            json={"dwell_time": 2001},
        )
        assert too_large.status_code == 422

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

    def test_user_specific_preferences_use_the_same_response_shape(self, prefs_user):
        """The user-scoped routes return the same defaults and mapped values."""
        user_id, username, user_type = prefs_user
        headers = create_test_headers(user_id, username, user_type)
        url = f"/api/auth/users/{user_id}/preferences"

        get_response = client.get(url, headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["tts_voice"] == "default"

        update_response = client.put(
            url,
            headers=headers,
            json={"tts_voice": "female", "high_contrast": True},
        )
        assert update_response.status_code == 200
        assert update_response.json()["tts_voice"] == "female"
        assert update_response.json()["high_contrast"] is True

    def test_preferences_no_auth(self):
        """Test that preferences require authentication"""
        response = client.get("/api/auth/preferences")
        assert response.status_code == 401

        response = client.put("/api/auth/preferences", json={"tts_voice": "female"})
        assert response.status_code == 401

    def test_empty_roster_teacher_cannot_manage_student_preferences(
        self, test_db_session
    ):
        """Teachers without a roster cannot access another student's preferences."""
        teacher = User(
            username="prefs_empty_roster_teacher",
            password_hash="test-hash",
            display_name="Empty Roster Teacher",
            user_type="teacher",
        )
        student = User(
            username="prefs_empty_roster_student",
            password_hash="test-hash",
            display_name="Empty Roster Student",
            user_type="student",
        )
        test_db_session.add_all([teacher, student])
        test_db_session.commit()
        test_db_session.refresh(teacher)
        test_db_session.refresh(student)
        headers = create_test_headers(teacher.id, teacher.username, teacher.user_type)
        url = f"/api/auth/users/{student.id}/preferences"

        assert client.get(url, headers=headers).status_code == 403
        response = client.put(
            url,
            headers=headers,
            json={"high_contrast": True},
        )
        assert response.status_code == 403

    def test_rostered_teacher_cannot_manage_unassigned_student_preferences(
        self, test_db_session
    ):
        """Once a roster exists, preference access is limited to assigned students."""
        teacher = User(
            username="prefs_scoped_teacher",
            password_hash="test-hash",
            display_name="Scoped Teacher",
            user_type="teacher",
        )
        assigned_student = User(
            username="prefs_assigned_student",
            password_hash="test-hash",
            display_name="Assigned Student",
            user_type="student",
        )
        unassigned_student = User(
            username="prefs_unassigned_student",
            password_hash="test-hash",
            display_name="Unassigned Student",
            user_type="student",
        )
        test_db_session.add_all([teacher, assigned_student, unassigned_student])
        test_db_session.commit()
        test_db_session.refresh(teacher)
        test_db_session.refresh(unassigned_student)
        test_db_session.add(
            StudentTeacher(teacher_id=teacher.id, student_id=assigned_student.id)
        )
        test_db_session.commit()

        headers = create_test_headers(teacher.id, teacher.username, teacher.user_type)
        url = f"/api/auth/users/{unassigned_student.id}/preferences"
        assert client.get(url, headers=headers).status_code == 403
        assert client.put(
            url,
            headers=headers,
            json={"high_contrast": True},
        ).status_code == 403


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

    def test_explicit_null_email_clears_existing_email(self, prefs_user, test_db_session):
        """An explicit null clears an optional email instead of being ignored."""
        user_id, username, user_type = prefs_user
        user = test_db_session.get(User, user_id)
        user.email = "existing@test.com"
        test_db_session.commit()

        response = client.put(
            "/api/auth/profile",
            headers=create_test_headers(user_id, username, user_type),
            json={"email": None},
        )

        assert response.status_code == 200
        assert response.json()["email"] is None
        test_db_session.refresh(user)
        assert user.email is None

    def test_blank_display_name_is_rejected(self, prefs_user):
        """Profile saves must not leave the account without a display name."""
        user_id, username, user_type = prefs_user
        response = client.put(
            "/api/auth/profile",
            headers=create_test_headers(user_id, username, user_type),
            json={"display_name": "   "},
        )
        assert response.status_code == 400

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
