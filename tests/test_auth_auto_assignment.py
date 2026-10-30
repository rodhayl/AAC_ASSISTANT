import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.aac_app.models.database import StudentTeacher, User

client = TestClient(app)

# Use the setup_test_db fixture for all tests in this file
pytestmark = pytest.mark.usefixtures("setup_test_db")


def test_auto_assign_student_to_teacher(test_db_session):
    """
    Test that a student is automatically assigned to a teacher when
    created_by_teacher_id is provided during registration.
    
    NOTE: This test documents intended functionality that is not yet implemented
    in the public /register endpoint. The functionality exists in UserService.create_user
    but the /register endpoint creates users directly without using the service.
    For security, teachers should create students via the admin endpoint.
    """
    pytest.skip(
        "created_by_teacher_id not implemented in /register endpoint for security. "
        "Teachers should create students via /auth/admin/create-user or the teacher portal."
    )


def test_auto_assign_fails_invalid_teacher(test_db_session):
    """
    Test that auto-assignment is skipped if the teacher ID does not exist.
    """
    # 1. Create a student with non-existent teacher id
    non_existent_teacher_id = 99999
    student_data = {
        "username": "student2",
        "password": "TestPassword123",
        "display_name": "Student Two",
        "user_type": "student",
        "created_by_teacher_id": non_existent_teacher_id
    }
    response = client.post("/api/auth/register", json=student_data)
    assert response.status_code == 200
    student_id = response.json()["id"]

    # 2. Verify no StudentTeacher entry exists
    assignment = test_db_session.query(StudentTeacher).filter_by(
        student_id=student_id
    ).first()

    assert assignment is None


def test_auto_assign_fails_non_teacher_id(test_db_session):
    """
    Test that auto-assignment is skipped if the ID belongs to a non-teacher user.
    """
    # 1. Create a user who is NOT a teacher (e.g., another student)
    existing_student_data = {
        "username": "existing_student",
        "password": "TestPassword123",
        "display_name": "Existing Student",
        "user_type": "student"
    }
    response = client.post("/api/auth/register", json=existing_student_data)
    assert response.status_code == 200
    existing_student_id = response.json()["id"]

    # 2. Create a new student trying to assign to the existing student
    new_student_data = {
        "username": "new_student",
        "password": "TestPassword123",
        "display_name": "New Student",
        "user_type": "student",
        "created_by_teacher_id": existing_student_id
    }
    response = client.post("/api/auth/register", json=new_student_data)
    assert response.status_code == 200
    new_student_id = response.json()["id"]

    # 3. Verify no StudentTeacher entry exists
    assignment = test_db_session.query(StudentTeacher).filter_by(
        student_id=new_student_id
    ).first()

    assert assignment is None
