"""Real-case API coverage for the users and achievements routers.

Covers the profile-update endpoint, teacher-scoped student listing,
student-assignment permission/error paths, password-reset permission rules,
and the achievements teacher/admin-only permission branches plus the delete
flow.
"""
import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import Achievement, StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.utils.jwt_utils import create_access_token
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


@pytest.fixture
def teacher_user(test_db_session):
    user = User(
        username="coverage_teacher",
        display_name="Coverage Teacher",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def student_user(test_db_session):
    user = User(
        username="coverage_student",
        display_name="Coverage Student",
        user_type="student",
        password_hash=get_password_hash("StudentPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


def _token(user):
    return create_access_token(
        data={"sub": user.username, "user_id": user.id, "user_type": user.user_type}
    )


def test_update_current_user_profile(regular_user, user_token):
    response = client.put(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"display_name": "Nuevo Nombre", "email": "new@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Nuevo Nombre"


def test_teacher_students_list_scoped_to_roster(
    teacher_user, student_user, test_db_session
):
    """A teacher only sees students in their explicit roster."""
    other = User(
        username="coverage_unassigned",
        display_name="Unassigned Student",
        user_type="student",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(other)
    test_db_session.flush()
    test_db_session.add(StudentTeacher(teacher_id=teacher_user.id, student_id=student_user.id))
    test_db_session.commit()

    response = client.get(
        "/api/users/students",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 200
    usernames = [u["username"] for u in response.json()]
    assert student_user.username in usernames
    assert other.username not in usernames


def test_student_cannot_create_students(student_user):
    response = client.post(
        "/api/users/students",
        headers=create_test_headers(student_user.id, student_user.username, "student"),
        json={
            "username": "sneaky_student",
            "password": "StudentPass123",
            "display_name": "Sneaky",
        },
    )
    assert response.status_code == 403


def test_assign_student_permission_and_error_paths(
    teacher_user, student_user, regular_user, user_token, admin_user
):
    """Assignment enforces role, self-only for teachers, and existence checks."""
    # Students cannot assign.
    res = client.post(
        "/api/users/assign-student",
        headers=create_test_headers(regular_user.id, regular_user.username, "standard"),
        json={"student_id": student_user.id, "teacher_id": teacher_user.id},
    )
    assert res.status_code == 403

    # A teacher can only assign to themselves.
    res = client.post(
        "/api/users/assign-student",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
        json={"student_id": student_user.id, "teacher_id": regular_user.id},
    )
    assert res.status_code == 403

    # Missing student -> 404.
    res = client.post(
        "/api/users/assign-student",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
        json={"student_id": 999999, "teacher_id": teacher_user.id},
    )
    assert res.status_code == 404

    # Missing teacher -> 404 (admins may target any teacher id).
    res = client.post(
        "/api/users/assign-student",
        headers=create_test_headers(admin_user.id, admin_user.username, "admin"),
        json={"student_id": student_user.id, "teacher_id": 999999},
    )
    assert res.status_code == 404

    # Successful assignment -> 201, repeat -> already exists.
    payload = {"student_id": student_user.id, "teacher_id": teacher_user.id}
    res = client.post(
        "/api/users/assign-student",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
        json=payload,
    )
    assert res.status_code == 201
    res = client.post(
        "/api/users/assign-student",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
        json=payload,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "exists"


def test_unassign_student_permission_and_404(teacher_user, student_user):
    teacher_headers = create_test_headers(
        teacher_user.id, teacher_user.username, "teacher"
    )
    # No assignment yet -> 404.
    res = client.delete(
        f"/api/users/assign-student/{student_user.id}/{teacher_user.id}",
        headers=teacher_headers,
    )
    assert res.status_code == 404

    # Create then remove the assignment.
    client.post(
        "/api/users/assign-student",
        headers=teacher_headers,
        json={"student_id": student_user.id, "teacher_id": teacher_user.id},
    )
    res = client.delete(
        f"/api/users/assign-student/{student_user.id}/{teacher_user.id}",
        headers=teacher_headers,
    )
    assert res.status_code == 200
    assert "removed" in res.json()["message"]


def test_reset_password_permission_rules(
    teacher_user, student_user, test_db_session
):
    """Password reset: students denied; teachers limited to assigned students."""
    student_headers = create_test_headers(
        student_user.id, student_user.username, "student"
    )
    res = client.post(
        "/api/users/reset-password",
        headers=student_headers,
        json={"user_id": student_user.id, "new_password": "NewPassword123"},
    )
    assert res.status_code == 403

    teacher_headers = create_test_headers(
        teacher_user.id, teacher_user.username, "teacher"
    )
    # Teacher cannot reset a non-student.
    res = client.post(
        "/api/users/reset-password",
        headers=teacher_headers,
        json={"user_id": teacher_user.id, "new_password": "NewPassword123"},
    )
    assert res.status_code == 403

    # Teacher cannot reset an unassigned student.
    res = client.post(
        "/api/users/reset-password",
        headers=teacher_headers,
        json={"user_id": student_user.id, "new_password": "NewPassword123"},
    )
    assert res.status_code == 403

    # Missing user -> 404.
    res = client.post(
        "/api/users/reset-password",
        headers=teacher_headers,
        json={"user_id": 999999, "new_password": "NewPassword123"},
    )
    assert res.status_code == 404

    # Teacher can reset an assigned student; new password works at login.
    test_db_session.add(
        StudentTeacher(teacher_id=teacher_user.id, student_id=student_user.id)
    )
    test_db_session.commit()
    res = client.post(
        "/api/users/reset-password",
        headers=teacher_headers,
        json={"user_id": student_user.id, "new_password": "NewPassword123"},
    )
    assert res.status_code == 200

    login = client.post(
        "/api/auth/token",
        data={"username": student_user.username, "password": "NewPassword123"},
    )
    assert login.status_code == 200


def test_achievement_staff_endpoints_deny_students(student_user):
    """All achievement-management endpoints are teacher/admin only."""
    headers = create_test_headers(student_user.id, student_user.username, "student")
    assert client.get("/api/achievements/categories", headers=headers).status_code == 403
    assert (
        client.get("/api/achievements/criteria-types", headers=headers).status_code == 403
    )
    assert client.get("/api/achievements/", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/achievements/",
            json={"name": "X", "description": "Y", "category": "custom"},
            headers=headers,
        ).status_code
        == 403
    )


def test_achievement_delete_permissions_and_flow(
    test_db_session, teacher_user, admin_token, admin_user
):
    """Deleting achievements: 404, system-protected, own-custom allowed."""
    headers = create_test_headers(teacher_user.id, teacher_user.username, "teacher")

    # Missing -> 404.
    assert (
        client.delete(
            "/api/achievements/999999",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).status_code
        == 404
    )

    # Teacher cannot delete a system achievement.
    system = Achievement(
        name="System", description="S", category="general", points=10, created_by=None
    )
    test_db_session.add(system)
    test_db_session.commit()
    test_db_session.refresh(system)
    assert client.delete(f"/api/achievements/{system.id}", headers=headers).status_code == 403

    # System achievements cannot be deleted by anyone, including admins.
    assert (
        client.delete(
            f"/api/achievements/{system.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).status_code
        == 403
    )

    # A teacher cannot delete another teacher's custom achievement.
    other_teacher = User(
        username="coverage_other_teacher",
        display_name="Other Teacher",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(other_teacher)
    test_db_session.commit()
    custom = Achievement(
        name="Custom",
        description="C",
        category="custom",
        points=5,
        created_by=other_teacher.id,
        is_manual=True,
    )
    test_db_session.add(custom)
    test_db_session.commit()
    test_db_session.refresh(custom)
    assert client.delete(f"/api/achievements/{custom.id}", headers=headers).status_code == 403

    # The creator can delete their own.
    own = Achievement(
        name="Own", description="O", category="custom", points=5, created_by=teacher_user.id
    )
    test_db_session.add(own)
    test_db_session.commit()
    test_db_session.refresh(own)
    assert client.delete(f"/api/achievements/{own.id}", headers=headers).status_code == 204


def test_achievement_categories_and_criteria_success(teacher_user):
    """Teachers can read the predefined categories and criteria types."""
    headers = create_test_headers(teacher_user.id, teacher_user.username, "teacher")

    res = client.get("/api/achievements/categories", headers=headers)
    assert res.status_code == 200
    assert "custom" in res.json()

    res = client.get("/api/achievements/criteria-types", headers=headers)
    assert res.status_code == 200
    assert "sessions_completed" in res.json()


def test_achievement_update_permission_and_error_paths(
    teacher_user, student_user, test_db_session
):
    """Update enforces staff-only, 404, own-only and system-protection rules."""
    student_headers = create_test_headers(
        student_user.id, student_user.username, "student"
    )
    assert (
        client.put(
            "/api/achievements/1", json={"name": "X"}, headers=student_headers
        ).status_code
        == 403
    )

    teacher_headers = create_test_headers(
        teacher_user.id, teacher_user.username, "teacher"
    )
    # Missing achievement -> 404.
    assert (
        client.put(
            "/api/achievements/999999", json={"name": "X"}, headers=teacher_headers
        ).status_code
        == 404
    )

    # A teacher cannot update another teacher's custom achievement.
    other = User(
        username="coverage_other_t2",
        display_name="Other Teacher 2",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(other)
    test_db_session.commit()
    custom = Achievement(
        name="Other Custom",
        description="",
        category="custom",
        points=5,
        created_by=other.id,
        is_manual=True,
    )
    test_db_session.add(custom)
    test_db_session.commit()
    test_db_session.refresh(custom)
    assert (
        client.put(
            f"/api/achievements/{custom.id}",
            json={"name": "Hijacked"},
            headers=teacher_headers,
        ).status_code
        == 403
    )

    # A teacher cannot update a system achievement (created_by=None).
    system = Achievement(
        name="Sys", description="", category="general", points=10, created_by=None
    )
    test_db_session.add(system)
    test_db_session.commit()
    test_db_session.refresh(system)
    assert (
        client.put(
            f"/api/achievements/{system.id}",
            json={"name": "Nope"},
            headers=teacher_headers,
        ).status_code
        == 403
    )


def test_achievement_update_all_fields_by_creator(teacher_user, test_db_session):
    """The creator can update every field; criteria presence flips is_manual."""
    own = Achievement(
        name="Own",
        description="D",
        category="custom",
        points=5,
        icon="⭐",
        created_by=teacher_user.id,
        is_manual=True,
    )
    test_db_session.add(own)
    test_db_session.commit()
    test_db_session.refresh(own)
    headers = create_test_headers(teacher_user.id, teacher_user.username, "teacher")

    res = client.put(
        f"/api/achievements/{own.id}",
        headers=headers,
        json={
            "name": "Renamed",
            "description": "New description",
            "category": "learning",
            "points": 20,
            "icon": "🔥",
            "is_active": True,
            "criteria_type": "sessions_completed",
            "criteria_value": 3,
        },
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed"
    assert res.json()["description"] == "New description"
    assert res.json()["category"] == "learning"
    assert res.json()["points"] == 20
    assert res.json()["icon"] == "🔥"
    assert res.json()["criteria_type"] == "sessions_completed"
    assert res.json()["criteria_value"] == 3
    assert res.json()["is_manual"] is False


def test_achievement_delete_denies_students(student_user):
    headers = create_test_headers(student_user.id, student_user.username, "student")
    assert (
        client.delete("/api/achievements/1", headers=headers).status_code == 403
    )


def test_achievement_award_permissions_errors_and_success(
    teacher_user, student_user, test_db_session
):
    """Award enforces staff-only, existence, roster access, and duplicate checks."""
    student_headers = create_test_headers(
        student_user.id, student_user.username, "student"
    )
    assert (
        client.post(
            "/api/achievements/1/award",
            json={"user_id": student_user.id},
            headers=student_headers,
        ).status_code
        == 403
    )

    teacher_headers = create_test_headers(
        teacher_user.id, teacher_user.username, "teacher"
    )
    # Missing achievement -> 404.
    assert (
        client.post(
            "/api/achievements/999999/award",
            json={"user_id": student_user.id},
            headers=teacher_headers,
        ).status_code
        == 404
    )

    # A teacher cannot award to a student outside their roster.
    custom = Achievement(
        name="Awardable",
        description="",
        category="custom",
        points=5,
        created_by=teacher_user.id,
        is_manual=True,
    )
    test_db_session.add(custom)
    test_db_session.commit()
    test_db_session.refresh(custom)
    assert (
        client.post(
            f"/api/achievements/{custom.id}/award",
            json={"user_id": student_user.id},
            headers=teacher_headers,
        ).status_code
        == 403
    )

    # Add the student to the roster: award succeeds once, duplicate -> 400.
    test_db_session.add(
        StudentTeacher(teacher_id=teacher_user.id, student_id=student_user.id)
    )
    test_db_session.commit()
    res = client.post(
        f"/api/achievements/{custom.id}/award",
        json={"user_id": student_user.id},
        headers=teacher_headers,
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Awardable"
    assert res.json()["progress"] == 1.0

    res = client.post(
        f"/api/achievements/{custom.id}/award",
        json={"user_id": student_user.id},
        headers=teacher_headers,
    )
    assert res.status_code == 400
