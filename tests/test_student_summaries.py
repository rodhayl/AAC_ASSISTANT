from fastapi.testclient import TestClient

from src.aac_app.models import BoardAssignment, CommunicationBoard, StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)


def create_user(session, username, role):
    user = User(
        username=username,
        display_name=username,
        user_type=role,
        password_hash=get_password_hash("StrongPass123"),
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_student_summaries_are_bulk_and_teacher_scoped(setup_test_db, test_db_session):
    admin = create_user(test_db_session, "summary_admin", "admin")
    teacher = create_user(test_db_session, "summary_teacher", "teacher")
    visible = create_user(test_db_session, "summary_visible", "student")
    hidden = create_user(test_db_session, "summary_hidden", "student")
    board = CommunicationBoard(
        user_id=teacher.id,
        name="Summary Board",
        description="A lightweight board summary",
        category="general",
    )
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)
    test_db_session.add(StudentTeacher(student_id=visible.id, teacher_id=teacher.id))
    test_db_session.add(BoardAssignment(board_id=board.id, student_id=visible.id, assigned_by=teacher.id))
    test_db_session.commit()

    teacher_response = client.get(
        "/api/auth/users/student-summaries",
        params={"limit": 100},
        headers=create_test_headers(teacher.id, teacher.username, teacher.user_type),
    )
    assert teacher_response.status_code == 200
    teacher_data = teacher_response.json()
    assert [item["id"] for item in teacher_data] == [visible.id]
    assert teacher_data[0]["assigned_boards"][0]["id"] == board.id

    admin_response = client.get(
        "/api/auth/users/student-summaries",
        headers=create_test_headers(admin.id, admin.username, admin.user_type),
    )
    assert admin_response.status_code == 200
    admin_ids = {item["id"] for item in admin_response.json()}
    assert {visible.id, hidden.id}.issubset(admin_ids)


def test_empty_roster_teacher_gets_no_student_summaries(setup_test_db, test_db_session):
    teacher = create_user(test_db_session, "summary_empty_teacher", "teacher")
    create_user(test_db_session, "summary_unassigned_student", "student")

    response = client.get(
        "/api/auth/users/student-summaries",
        headers=create_test_headers(teacher.id, teacher.username, teacher.user_type),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_promoted_student_does_not_resurface_in_teacher_student_lists(
    setup_test_db, test_db_session
):
    """After an admin promotes a roster member out of the student role, the
    stale roster row must not make the account reappear in the teacher's
    student lists (both the summaries endpoint and /users/students)."""
    teacher = create_user(test_db_session, "summary_promote_teacher", "teacher")
    promoted = create_user(test_db_session, "summary_promoted", "student")
    test_db_session.add(StudentTeacher(student_id=promoted.id, teacher_id=teacher.id))
    test_db_session.commit()

    # Promote the roster member to teacher, leaving the roster row behind.
    promoted.user_type = "teacher"
    test_db_session.commit()

    headers = create_test_headers(teacher.id, teacher.username, teacher.user_type)
    summaries = client.get(
        "/api/auth/users/student-summaries",
        params={"limit": 100},
        headers=headers,
    )
    assert summaries.status_code == 200
    assert all(item["id"] != promoted.id for item in summaries.json())

    students = client.get("/api/users/students", headers=headers)
    assert students.status_code == 200
    assert all(item["id"] != promoted.id for item in students.json())
