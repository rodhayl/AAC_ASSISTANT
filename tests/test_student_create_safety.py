"""Optional per-student safety configuration at account creation.

Covers both staff creation endpoints (teacher POST /users/students and admin
POST /auth/admin/create-user): creating a student with age / filter level /
forbidden topics / feature gates in one step, creating without any safety data
(no guardian profile), teacher rejection of admin-locked fields, and the admin
bypass that lets admins set locked fields (they define the locks).
"""
import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import GuardianProfile, StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.auth_helpers import create_test_token

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("setup_test_db")


def _make_user(test_db_session, username, user_type, password="TestPassword123"):
    user = User(
        username=username,
        email=f"{username}@test.com",
        password_hash=get_password_hash(password),
        user_type=user_type,
        is_active=True,
        display_name=username.title(),
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


def _headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_test_token(user.id, user.username, user.user_type)}"
    }


def _profile_of(db, user_id):
    return db.query(GuardianProfile).filter_by(user_id=user_id).first()


def _set_global_lock(admin, *, locked_fields, feature_locks=None):
    """Set the admin global content-safety policy (and cache-clear) via API."""
    client.put(
        "/api/settings/content-safety",
        headers=_headers(admin),
        json={
            "level": "standard",
            "forbidden_topics": [],
            "trigger_words": [],
            "feature_locks": feature_locks or {},
            "sentinel_moderation": False,
            "max_response_length": None,
            "locked_fields": locked_fields,
        },
    )
    from src.api.deps.settings import clear_settings_cache

    clear_settings_cache()


def test_teacher_create_student_without_safety_leaves_no_profile(
    test_db_session,
):
    teacher = _make_user(test_db_session, "create_teacher0", "teacher")

    resp = client.post(
        "/api/users/students",
        headers=_headers(teacher),
        json={
            "username": "plain_student",
            "password": "PlainPass123",
            "display_name": "Plain Student",
            "user_type": "student",
        },
    )
    assert resp.status_code == 200, resp.text

    student = (
        test_db_session.query(User).filter_by(username="plain_student").first()
    )
    assert student is not None
    assert _profile_of(test_db_session, student.id) is None
    # The teacher is still auto-assigned to the new student.
    assert (
        test_db_session.query(StudentTeacher)
        .filter_by(teacher_id=teacher.id, student_id=student.id)
        .first()
        is not None
    )


def test_teacher_create_student_with_safety_creates_profile(test_db_session):
    teacher = _make_user(test_db_session, "create_teacher1", "teacher")

    resp = client.post(
        "/api/users/students",
        headers=_headers(teacher),
        json={
            "username": "safety_student1",
            "password": "SafetyPass123",
            "display_name": "Safety Student",
            "user_type": "student",
            "safety": {
                "age": 7,
                "content_filter_level": "strict",
                "forbidden_topics": ["astronomía"],
                "trigger_words": ["guerra"],
                "block_ai_chat": True,
                "block_custom_topics": False,
            },
        },
    )
    assert resp.status_code == 200, resp.text

    student = (
        test_db_session.query(User).filter_by(username="safety_student1").first()
    )
    profile = _profile_of(test_db_session, student.id)
    assert profile is not None
    assert profile.age == 7
    constraints = profile.safety_constraints or {}
    assert constraints["content_filter_level"] == "strict"
    assert constraints["forbidden_topics"] == ["astronomía"]
    assert constraints["trigger_words"] == ["guerra"]
    assert constraints["block_ai_chat"] is True
    assert constraints["block_custom_topics"] is False


def test_admin_create_student_with_safety(test_db_session):
    admin = _make_user(test_db_session, "create_admin1", "admin")

    resp = client.post(
        "/api/auth/admin/create-user",
        headers=_headers(admin),
        json={
            "username": "admin_safety_student",
            "password": "AdminPass123",
            "confirm_password": "AdminPass123",
            "display_name": "Admin Safety Student",
            "user_type": "student",
            "safety": {
                "age": 10,
                "content_filter_level": "standard",
                "block_social_messaging": True,
            },
        },
    )
    assert resp.status_code == 200, resp.text

    student = (
        test_db_session.query(User)
        .filter_by(username="admin_safety_student")
        .first()
    )
    profile = _profile_of(test_db_session, student.id)
    assert profile is not None
    assert profile.age == 10
    assert (profile.safety_constraints or {})["block_social_messaging"] is True
    assert (profile.safety_constraints or {})["content_filter_level"] == "standard"


def test_teacher_cannot_set_admin_locked_field_at_creation(test_db_session):
    admin = _make_user(test_db_session, "create_admin2", "admin")
    teacher = _make_user(test_db_session, "create_teacher2", "teacher")
    _set_global_lock(admin, locked_fields=["block_ai_chat"])

    try:
        resp = client.post(
            "/api/users/students",
            headers=_headers(teacher),
            json={
                "username": "locked_student",
                "password": "LockedPass123",
                "display_name": "Locked Student",
                "user_type": "student",
                "safety": {"block_ai_chat": True, "block_board_ai": True},
            },
        )
        assert resp.status_code == 403
        assert "block_ai_chat" in resp.json()["detail"]
        # The user must not exist: creation is atomic.
        assert (
            test_db_session.query(User).filter_by(username="locked_student").first()
            is None
        )
    finally:
        _set_global_lock(admin, locked_fields=[])


def test_admin_can_set_locked_field_at_creation(test_db_session):
    admin = _make_user(test_db_session, "create_admin3", "admin")
    _set_global_lock(admin, locked_fields=["block_ai_chat"])

    try:
        resp = client.post(
            "/api/auth/admin/create-user",
            headers=_headers(admin),
            json={
                "username": "admin_locked_student",
                "password": "AdminPass123",
                "confirm_password": "AdminPass123",
                "display_name": "Admin Locked Student",
                "user_type": "student",
                "safety": {"block_ai_chat": True},
            },
        )
        assert resp.status_code == 200, resp.text

        student = (
            test_db_session.query(User)
            .filter_by(username="admin_locked_student")
            .first()
        )
        profile = _profile_of(test_db_session, student.id)
        assert profile is not None
        assert (profile.safety_constraints or {})["block_ai_chat"] is True
    finally:
        _set_global_lock(admin, locked_fields=[])


def test_invalid_filter_level_rejected(test_db_session):
    teacher = _make_user(test_db_session, "create_teacher3", "teacher")

    resp = client.post(
        "/api/users/students",
        headers=_headers(teacher),
        json={
            "username": "bad_level_student",
            "password": "BadLevel123",
            "display_name": "Bad Level Student",
            "user_type": "student",
            "safety": {"content_filter_level": "moderate"},
        },
    )
    assert resp.status_code == 400
    assert (
        test_db_session.query(User).filter_by(username="bad_level_student").first()
        is None
    )


def test_safety_ignored_for_non_student_roles(test_db_session):
    admin = _make_user(test_db_session, "create_admin4", "admin")

    resp = client.post(
        "/api/auth/admin/create-user",
        headers=_headers(admin),
        json={
            "username": "safety_teacher_account",
            "password": "AdminPass123",
            "confirm_password": "AdminPass123",
            "display_name": "Safety Teacher",
            "user_type": "teacher",
            "safety": {"age": 7, "block_ai_chat": True},
        },
    )
    assert resp.status_code == 200, resp.text
    teacher = (
        test_db_session.query(User)
        .filter_by(username="safety_teacher_account")
        .first()
    )
    assert _profile_of(test_db_session, teacher.id) is None
