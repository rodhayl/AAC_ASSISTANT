"""Write routes must commit before responding.

FastAPI resumes a yield dependency's teardown *after* the response is sent, so
``get_db``'s teardown commit is too late for flows where the client re-reads
the data right after a write (register then login, create student then list,
save settings then rebuild the provider, end session then view achievements).

These tests replace the request-scoped DB dependency with a session whose
teardown deliberately does NOT commit. A route that relied solely on the
deferred teardown commit would lose its write; routes that commit before
responding keep the data durable and visible to a fresh session.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from src.aac_app.models import (
    AppSettings,
    GuardianProfile,
    LearningSession,
    Symbol,
    SymbolUsageLog,
    User,
    UserAchievement,
    UserSettings,
)
from src.aac_app.services.auth_service import get_password_hash, verify_password
from src.api.deps import get_db
from src.api.main import app
from tests.auth_helpers import create_test_token

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


@pytest.fixture
def no_teardown_commit_db(setup_test_db, test_db_engine):
    """Serve request sessions whose teardown never commits.

    Simulates a client racing the response: the write must already be durable
    when the client makes its next request, because the request-scoped
    dependency's deferred commit has not run yet.
    """

    TestingSessionLocal = sessionmaker(
        bind=test_db_engine,
        autocommit=False,
        autoflush=False,
    )

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.rollback()
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def _fresh_session(test_db_engine):
    """Open a session independent of any request-scoped transaction."""
    return sessionmaker(bind=test_db_engine)()


def _token(user_id: int, username: str, user_type: str = "student") -> dict:
    return {
        "Authorization": f"Bearer {create_test_token(user_id, username, user_type)}"
    }


def _make_user(test_db_session, username: str, user_type: str, password: str) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=get_password_hash(password),
        user_type=user_type,
        is_active=True,
        display_name=username.title(),
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


class TestAuthWrites:
    def test_register_is_durable_before_response(self, no_teardown_commit_db, test_db_engine):
        """A self-registered account must be usable by the follow-up login."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "durable_register",
                "password": "StrongPass123",
                "display_name": "Durable Register",
            },
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            user = (
                session.query(User)
                .filter(User.username == "durable_register")
                .first()
            )
        assert user is not None
        assert verify_password("StrongPass123", user.password_hash)

    def test_admin_create_user_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """An admin-created account must be readable by the follow-up login."""
        admin = _make_user(test_db_session, "durable_admin", "admin", test_password)

        response = client.post(
            "/api/auth/admin/create-user",
            headers=_token(admin.id, admin.username, "admin"),
            json={
                "username": "durable_student",
                "password": test_password,
                "confirm_password": test_password,
                "display_name": "Durable Student",
                "user_type": "student",
            },
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            user = (
                session.query(User)
                .filter(User.username == "durable_student")
                .first()
            )
        assert user is not None
        assert user.user_type == "student"

    def test_admin_create_user_is_visible_to_immediate_list(
        self, no_teardown_commit_db, test_db_session, test_password
    ):
        """A list refresh immediately after creation must include the new user."""
        admin = _make_user(test_db_session, "durable_list_admin", "admin", test_password)
        headers = _token(admin.id, admin.username, "admin")
        payload = {
            "username": "durable_list_teacher",
            "password": test_password,
            "confirm_password": test_password,
            "display_name": "Durable List Teacher",
            "user_type": "teacher",
        }

        created = client.post(
            "/api/auth/admin/create-user",
            headers=headers,
            json=payload,
        )
        assert created.status_code == 200, created.text
        created_id = created.json()["id"]

        listed = client.get(
            "/api/auth/users",
            params={"limit": 1000, "user_type": "teacher"},
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        assert any(
            user["id"] == created_id and user["username"] == payload["username"]
            for user in listed.json()
        )

    def test_change_password_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """A password change must be visible to the immediate re-login."""
        user = _make_user(test_db_session, "durable_changer", "student", test_password)

        response = client.post(
            "/api/auth/change-password",
            headers=_token(user.id, user.username, "student"),
            json={
                "username": user.username,
                "current_password": test_password,
                "new_password": "NewStrongPass456",
                "confirm_password": "NewStrongPass456",
            },
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            reloaded = session.get(User, user.id)
        assert reloaded is not None
        assert verify_password("NewStrongPass456", reloaded.password_hash)
        assert not verify_password(test_password, reloaded.password_hash)


class TestUserServiceWrites:
    def test_create_student_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """A created student must appear in the immediate list refresh."""
        admin = _make_user(test_db_session, "durable_admin_s", "admin", test_password)

        response = client.post(
            "/api/users/students",
            headers=_token(admin.id, admin.username, "admin"),
            json={
                "username": "durable_new_student",
                "password": test_password,
                "display_name": "New Student",
                "user_type": "student",
            },
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            user = (
                session.query(User)
                .filter(User.username == "durable_new_student")
                .first()
            )
        assert user is not None
        assert user.user_type == "student"

    def test_reset_password_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """A reset password must be visible to the immediate login."""
        admin = _make_user(test_db_session, "durable_admin_r", "admin", test_password)
        student = _make_user(test_db_session, "durable_reset", "student", test_password)

        response = client.post(
            "/api/users/reset-password",
            headers=_token(admin.id, admin.username, "admin"),
            json={"user_id": student.id, "new_password": "ResetPass789"},
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            reloaded = session.get(User, student.id)
        assert verify_password("ResetPass789", reloaded.password_hash)

    def test_update_current_user_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """A profile update must be visible to the immediate re-read."""
        user = _make_user(test_db_session, "durable_updater", "student", test_password)

        response = client.put(
            "/api/auth/profile",
            headers=_token(user.id, user.username, "student"),
            json={"display_name": "Updated Name"},
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            reloaded = session.get(User, user.id)
        assert reloaded.display_name == "Updated Name"


class TestSettingsWrites:
    def test_update_ai_settings_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """Saved AI settings must be durable before the response is sent.

        The route commits the settings and then resets the provider
        singletons; a follow-up request that lazily constructs a provider
        reads the new settings from the database. With the deferred teardown
        commit alone, that provider would be built from the previous values.
        """
        admin = _make_user(test_db_session, "durable_settings", "admin", test_password)

        response = client.put(
            "/api/settings/ai",
            headers=_token(admin.id, admin.username, "admin"),
            json={
                "provider": "openrouter",
                "openrouter_model": "openai/gpt-4o-mini",
            },
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            provider_row = (
                session.query(AppSettings)
                .filter(AppSettings.setting_key == "ai_provider")
                .first()
            )
            model_row = (
                session.query(AppSettings)
                .filter(AppSettings.setting_key == "openrouter_model")
                .first()
            )
        assert provider_row is not None
        assert provider_row.setting_value == "openrouter"
        assert model_row is not None
        assert model_row.setting_value == "openai/gpt-4o-mini"


class TestGuardianProfileWrites:
    def test_create_profile_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """A saved guardian profile must appear in the immediate list refresh."""
        admin = _make_user(test_db_session, "durable_gp_admin", "admin", test_password)
        student = _make_user(
            test_db_session, "durable_gp_student", "student", test_password
        )

        response = client.post(
            f"/api/guardian-profiles/students/{student.id}",
            headers=_token(admin.id, admin.username, "admin"),
            json={"template_name": "default", "age": 8},
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            profile = (
                session.query(GuardianProfile)
                .filter(GuardianProfile.user_id == student.id)
                .first()
            )
        assert profile is not None
        assert profile.is_active is True
        assert profile.template_name == "default"


class TestAnalyticsWrites:
    def test_usage_logging_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """Analytics rows must be visible to the immediate follow-up read."""
        user = _make_user(test_db_session, "durable_analytics", "student", test_password)
        symbol = Symbol(
            label="hello",
            category="social",
            language="en",
            is_builtin=True,
        )
        test_db_session.add(symbol)
        test_db_session.commit()
        test_db_session.refresh(symbol)

        response = client.post(
            "/api/analytics/usage",
            headers=_token(user.id, user.username, "student"),
            json={
                "symbols": [
                    {
                        "id": symbol.id,
                        "label": symbol.label,
                        "category": symbol.category,
                    }
                ],
                "context_topic": "greetings",
            },
        )
        assert response.status_code == 201, response.text

        with _fresh_session(test_db_engine) as session:
            logs = (
                session.query(SymbolUsageLog)
                .filter(SymbolUsageLog.user_id == user.id)
                .all()
            )
        assert len(logs) == 1
        assert logs[0].symbol_id == symbol.id


class TestGuardianProfileMutationWrites:
    def test_update_profile_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """A profile update must be visible to the immediate follow-up read."""
        admin = _make_user(test_db_session, "durable_gp_update_admin", "admin", test_password)
        student = _make_user(
            test_db_session, "durable_gp_update_student", "student", test_password
        )

        created = client.post(
            f"/api/guardian-profiles/students/{student.id}",
            headers=_token(admin.id, admin.username, "admin"),
            json={"template_name": "default", "age": 8},
        )
        assert created.status_code == 200, created.text

        response = client.put(
            f"/api/guardian-profiles/students/{student.id}",
            headers=_token(admin.id, admin.username, "admin"),
            json={"age": 9, "change_reason": "birthday"},
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            profile = (
                session.query(GuardianProfile)
                .filter(GuardianProfile.user_id == student.id)
                .first()
            )
        assert profile is not None
        assert profile.age == 9

    def test_delete_profile_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """A soft-deleted profile must be inactive in a fresh session."""
        admin = _make_user(test_db_session, "durable_gp_delete_admin", "admin", test_password)
        student = _make_user(
            test_db_session, "durable_gp_delete_student", "student", test_password
        )

        created = client.post(
            f"/api/guardian-profiles/students/{student.id}",
            headers=_token(admin.id, admin.username, "admin"),
            json={"template_name": "default"},
        )
        assert created.status_code == 200, created.text

        response = client.delete(
            f"/api/guardian-profiles/students/{student.id}",
            headers=_token(admin.id, admin.username, "admin"),
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            profile = (
                session.query(GuardianProfile)
                .filter(GuardianProfile.user_id == student.id)
                .first()
            )
        assert profile is not None
        assert profile.is_active is False


class TestImportWrites:
    def test_import_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """Imported learning history must be visible to the immediate re-read."""
        from src.api.routers.export_import import compute_checksum

        user = _make_user(test_db_session, "durable_import", "student", test_password)

        base = {
            "meta": {
                "exported_at": "2026-01-01T00:00:00Z",
                "username": user.username,
            },
            "boards": [],
            "assignedBoards": [],
            "achievements": [],
            "totalPoints": 0,
            "learningHistory": [
                {
                    "topic_name": "animals",
                    "status": "completed",
                    "comprehension_score": 0.5,
                    "questions_asked": 2,
                    "questions_answered": 1,
                    "correct_answers": 1,
                    "started_at": "2026-01-01T10:00:00",
                    "ended_at": "2026-01-01T10:05:00",
                }
            ],
        }
        payload = {
            **base,
            "meta": {
                **base["meta"],
                "checksum_sha256": compute_checksum(base),
                "schema_version": "2",
            },
        }

        response = client.post(
            "/api/data/import",
            headers=_token(user.id, user.username, "student"),
            json=payload,
        )
        assert response.status_code == 200, response.text

        with _fresh_session(test_db_engine) as session:
            imported = (
                session.query(LearningSession)
                .filter(LearningSession.user_id == user.id)
                .all()
            )
        assert len(imported) == 1
        assert imported[0].topic_name == "animals"


class TestAchievementWrites:
    def test_check_achievements_is_durable_before_response(
        self, no_teardown_commit_db, test_db_engine, test_db_session, test_password
    ):
        """Awards from /check must be visible to the immediate achievement read."""
        student = _make_user(
            test_db_session, "durable_ach_student", "student", test_password
        )
        test_db_session.add(UserSettings(user_id=student.id, ui_language="en"))
        # One completed session satisfies the First Steps criteria
        # (sessions_completed >= 1).
        test_db_session.add(
            LearningSession(
                user_id=student.id,
                topic_name="animals",
                status="completed",
                comprehension_score=0.0,
                questions_asked=0,
                questions_answered=0,
                correct_answers=0,
                started_at=datetime.now(UTC).replace(tzinfo=None),
                ended_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        test_db_session.commit()

        response = client.post(
            f"/api/achievements/user/{student.id}/check",
            headers=_token(student.id, student.username, "student"),
        )
        assert response.status_code == 200, response.text

        from sqlalchemy.orm import joinedload

        with _fresh_session(test_db_engine) as session:
            awarded = (
                session.query(UserAchievement)
                .options(joinedload(UserAchievement.achievement))
                .filter(UserAchievement.user_id == student.id)
                .all()
            )
            assert any(
                ua.achievement is not None and ua.achievement.name == "First Steps"
                for ua in awarded
            )
