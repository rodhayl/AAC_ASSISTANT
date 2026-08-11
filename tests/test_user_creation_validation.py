from fastapi.testclient import TestClient

from src.aac_app.models import StudentTeacher, User
from src.api.main import app

client = TestClient(app)


def test_admin_student_creation_rejects_non_teacher_assignment(
    setup_test_db,
    test_db_session,
    admin_user,
    admin_token,
    test_password,
):
    non_teacher = User(
        username="assignment_target_student",
        display_name="Assignment Target Student",
        user_type="student",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(non_teacher)
    test_db_session.commit()

    response = client.post(
        "/api/users/students",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "created_student_invalid_assignment",
            "display_name": "Created Student",
            "user_type": "teacher",
            "password": test_password,
            "created_by_teacher_id": non_teacher.id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Teacher not found"
    assert (
        test_db_session.query(User)
        .filter(User.username == "created_student_invalid_assignment")
        .first()
        is None
    )


def test_admin_student_creation_rejects_inactive_teacher_assignment(
    setup_test_db,
    test_db_session,
    admin_token,
    test_password,
):
    inactive_teacher = User(
        username="inactive_assignment_teacher",
        display_name="Inactive Assignment Teacher",
        user_type="teacher",
        password_hash="test-hash",
        is_active=False,
    )
    test_db_session.add(inactive_teacher)
    test_db_session.commit()

    response = client.post(
        "/api/users/students",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "created_student_inactive_assignment",
            "display_name": "Created Student",
            "user_type": "student",
            "password": test_password,
            "created_by_teacher_id": inactive_teacher.id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Teacher not found"
    assert (
        test_db_session.query(User)
        .filter(User.username == "created_student_inactive_assignment")
        .first()
        is None
    )


def test_student_creation_assigns_to_active_teacher(
    setup_test_db,
    test_db_session,
    admin_user,
    admin_token,
    test_password,
):
    teacher = User(
        username="active_assignment_teacher",
        display_name="Active Assignment Teacher",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(teacher)
    test_db_session.commit()

    response = client.post(
        "/api/users/students",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "created_student_valid_assignment",
            "display_name": "Created Student",
            "user_type": "teacher",
            "password": test_password,
            "created_by_teacher_id": teacher.id,
        },
    )

    assert response.status_code == 200
    created_id = response.json()["id"]
    assignment = (
        test_db_session.query(StudentTeacher)
        .filter_by(student_id=created_id, teacher_id=teacher.id)
        .one()
    )
    assert assignment.student_id == created_id
