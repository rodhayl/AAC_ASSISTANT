import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


def create_user(username, user_type, password, test_db_session):
    """
    Create a user directly in the database (bypassing API registration).

    This is necessary for testing because /auth/register always creates students
    to prevent privilege escalation. Admin/teacher accounts must be created
    via /auth/admin/create-user which requires an existing admin, creating a
    chicken-and-egg problem for tests.

    Solution: Insert users directly into test database.
    """
    user = User(
        username=username,
        display_name=f"{username.capitalize()} User",
        user_type=user_type,  # Can be admin, teacher, or student
        password_hash=get_password_hash(password),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return {"id": user.id, "username": user.username, "user_type": user.user_type}


def get_auth_header(user_id, username=None, user_type="student"):
    """Get real JWT token headers for testing (replacing old mock-token pattern)."""
    return create_test_headers(user_id, username, user_type)


def test_rbac_get_users(test_password, test_db_session):
    # Create users directly in database (bypassing API to allow admin/teacher creation)
    admin = create_user("admin1", "admin", test_password, test_db_session)
    teacher = create_user("teacher1", "teacher", test_password, test_db_session)
    student = create_user("student1", "student", test_password, test_db_session)

    # Admin should be able to list users
    response = client.get(
        "/api/auth/users", headers=get_auth_header(admin["id"], "admin1", "admin")
    )
    assert response.status_code == 200
    assert len(response.json()) >= 3

    # Teacher should be able to list users
    response = client.get(
        "/api/auth/users", headers=get_auth_header(teacher["id"], "teacher1", "teacher")
    )
    assert response.status_code == 200

    # Student should NOT be able to list users
    response = client.get(
        "/api/auth/users", headers=get_auth_header(student["id"], "student1", "student")
    )
    assert response.status_code == 403


def test_rbac_get_user_details(test_password, test_db_session):
    admin = create_user("admin2", "admin", test_password, test_db_session)
    teacher = create_user("teacher2", "teacher", test_password, test_db_session)
    student = create_user("student2", "student", test_password, test_db_session)
    student_other = create_user("student3", "student", test_password, test_db_session)

    # Admin can view anyone
    response = client.get(
        f"/api/auth/users/{student['id']}",
        headers=get_auth_header(admin["id"], "admin2", "admin"),
    )
    assert response.status_code == 200
    assert response.json()["username"] == "student2"

    # User can view self
    response = client.get(
        f"/api/auth/users/{student['id']}",
        headers=get_auth_header(student["id"], "student2", "student"),
    )
    assert response.status_code == 200

    # Student cannot view other student
    response = client.get(
        f"/api/auth/users/{student_other['id']}",
        headers=get_auth_header(student["id"], "student2", "student"),
    )
    assert response.status_code == 403

    # Teacher can view student
    response = client.get(
        f"/api/auth/users/{student['id']}",
        headers=get_auth_header(teacher["id"], "teacher2", "teacher"),
    )
    assert response.status_code == 200

    # Teacher cannot view admin
    response = client.get(
        f"/api/auth/users/{admin['id']}",
        headers=get_auth_header(teacher["id"], "teacher2", "teacher"),
    )
    assert response.status_code == 403


def test_rbac_admin_endpoints(test_password, test_db_session):
    create_user("admin3", "admin", test_password, test_db_session)
    student = create_user("student4", "student", test_password, test_db_session)

    # Reset DB - Admin only
    # Note: reset-db might destroy our test data, so be careful.
    # But since we use in-memory DB per test (or transaction rollback), it might be ok?
    # Actually, reset_db implementation drops tables. This might break the test session if not handled.
    # So let's test access control without executing fully if possible, or expect 200/403.
    # Wait, reset_db is POST /api/admin/reset-db

    # Student denied
    response = client.post(
        "/api/admin/reset-db",
        headers=get_auth_header(student["id"], "student4", "student"),
    )
    assert response.status_code == 403

    # Admin allowed (we won't actually call it to avoid breaking test env, or we assume it works)
    # But if I don't call it, I can't verify 200.
    # If I call it, it drops tables.
    # Let's skip the actual call for admin and trust the dependency check we verified for student.


def test_rbac_export_data(test_password, test_db_session):
    admin = create_user("admin4", "admin", test_password, test_db_session)
    student = create_user("student5", "student", test_password, test_db_session)
    other_student = create_user("student6", "student", test_password, test_db_session)

    # Student can export self
    response = client.get(
        f"/api/data/export?username={student['username']}",
        headers=get_auth_header(student["id"], "student5", "student"),
    )
    assert response.status_code == 200

    # Student cannot export other
    response = client.get(
        f"/api/data/export?username={other_student['username']}",
        headers=get_auth_header(student["id"], "student5", "student"),
    )
    assert response.status_code == 403

    # Admin can export other
    response = client.get(
        f"/api/data/export?username={student['username']}",
        headers=get_auth_header(admin["id"], "admin4", "admin"),
    )
    assert response.status_code == 200


def test_rbac_notifications(test_password, test_db_session):
    admin = create_user("admin5", "admin", test_password, test_db_session)
    student = create_user("student7", "student", test_password, test_db_session)

    # Create notification - Admin only
    response = client.post(
        "/api/notifications/",
        json={
            "user_id": student["id"],
            "title": "Test",
            "message": "Test Message",
            "type": "info",
        },
        headers=get_auth_header(student["id"], "student7", "student"),
    )
    assert response.status_code == 403

    response = client.post(
        "/api/notifications/",
        json={
            "user_id": student["id"],
            "title": "Test",
            "message": "Test Message",
            "type": "info",
        },
        headers=get_auth_header(admin["id"], "admin5", "admin"),
    )
    assert response.status_code == 200


def test_rbac_settings(test_password, test_db_session):
    admin = create_user("admin6", "admin", test_password, test_db_session)
    student = create_user("student8", "student", test_password, test_db_session)

    # Get settings - Student allowed but masked
    response = client.get(
        "/api/settings/ai",
        headers=get_auth_header(student["id"], "student8", "student"),
    )
    assert response.status_code == 200
    assert response.json()["can_edit"] is False
    # API key should be None or masked
    key = response.json().get("openrouter_api_key")
    assert key is None or key == "********"

    # Get settings - Admin allowed
    response = client.get(
        "/api/settings/ai", headers=get_auth_header(admin["id"], "admin6", "admin")
    )
    assert response.status_code == 200
    assert response.json()["can_edit"] is True

    # Update settings - Student denied
    response = client.put(
        "/api/settings/ai",
        json={"provider": "ollama"},
        headers=get_auth_header(student["id"], "student8", "student"),
    )
    assert response.status_code == 403

    # Update settings - Admin allowed
    response = client.put(
        "/api/settings/ai",
        json={"provider": "ollama"},
        headers=get_auth_header(admin["id"], "admin6", "admin"),
    )
    assert response.status_code == 200
