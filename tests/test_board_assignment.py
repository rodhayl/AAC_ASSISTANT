import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import BoardAssignment, StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


@pytest.fixture(scope="function")
def teacher_and_student(test_db_session):
    teacher = User(
        username="teacher_assign",
        password_hash=get_password_hash("StrongPass123"),
        display_name="Teacher Assign",
        user_type="teacher",
    )
    student = User(
        username="student_assign",
        password_hash=get_password_hash("StrongPass123"),
        display_name="Student Assign",
        user_type="student",
    )
    test_db_session.add(teacher)
    test_db_session.add(student)
    test_db_session.flush()
    test_db_session.add(StudentTeacher(student_id=student.id, teacher_id=teacher.id))
    test_db_session.commit()
    return teacher, student


def test_board_assignment_flow(teacher_and_student, test_db_session):
    teacher, student = teacher_and_student

    teacher_headers = create_test_headers(teacher.id, "teacher_assign", "teacher")
    student_headers = create_test_headers(student.id, "student_assign", "student")

    # Create a board for the teacher
    res = client.post(
        "/api/boards/",
        json={
            "name": "Assignable Board",
            "description": "Board for assignment",
            "category": "general",
            "is_public": False,
            "is_template": False,
        },
        params={"user_id": teacher.id},
        headers=teacher_headers,
    )
    print("CREATE status:", res.status_code, "body:", res.text)
    assert res.status_code == 200
    board = res.json()
    board_id = board["id"]

    # Assign to student
    res2 = client.post(
        f"/api/boards/{board_id}/assign",
        json={"student_id": student.id, "assigned_by": teacher.id},
        headers=teacher_headers,
    )
    print("ASSIGN status:", res2.status_code, "body:", res2.text)
    assert res2.status_code == 200
    assert res2.json()["ok"] is True
    assignment = (
        test_db_session.query(BoardAssignment)
        .filter_by(board_id=board_id, student_id=student.id)
        .one()
    )
    assert assignment.assigned_by == teacher.id

    # Duplicate assign should be idempotent
    res2b = client.post(
        f"/api/boards/{board_id}/assign",
        json={"student_id": student.id, "assigned_by": teacher.id},
        headers=teacher_headers,
    )
    print("ASSIGN again status:", res2b.status_code, "body:", res2b.text)
    assert res2b.status_code == 200
    assert res2b.json()["ok"] is True

    # Get assigned boards
    res3 = client.get(
        "/api/boards/assigned",
        params={"student_id": student.id},
        headers=student_headers,
    )
    print("ASSIGNED LIST status:", res3.status_code, "body:", res3.text)
    assert res3.status_code == 200
    assigned = res3.json()
    assert any(b["id"] == board_id for b in assigned)

    # Unassign
    res4 = client.delete(
        f"/api/boards/{board_id}/assign/{student.id}", headers=teacher_headers
    )
    print("UNASSIGN status:", res4.status_code, "body:", res4.text)
    assert res4.status_code == 200
    assert res4.json()["ok"] is True

    # Verify no assigned boards remain
    res5 = client.get(
        "/api/boards/assigned",
        params={"student_id": student.id},
        headers=student_headers,
    )
    print("ASSIGNED AFTER UNASSIGN status:", res5.status_code, "body:", res5.text)
    assert res5.status_code == 200
    assert len(res5.json()) == 0


def test_student_board_owner_cannot_manage_assignments(teacher_and_student, test_db_session):
    _teacher, student = teacher_and_student
    other_student = User(
        username="student_assignment_target",
        password_hash=get_password_hash("StrongPass123"),
        display_name="Assignment Target",
        user_type="student",
    )
    test_db_session.add(other_student)
    test_db_session.commit()

    student_headers = create_test_headers(student.id, student.username, student.user_type)
    create_response = client.post(
        "/api/boards/",
        json={"name": "Student-owned board", "category": "general"},
        params={"user_id": student.id},
        headers=student_headers,
    )
    assert create_response.status_code == 200
    board_id = create_response.json()["id"]

    assign_response = client.post(
        f"/api/boards/{board_id}/assign",
        json={"student_id": other_student.id},
        headers=student_headers,
    )
    assert assign_response.status_code == 403

    unassign_response = client.delete(
        f"/api/boards/{board_id}/assign/{other_student.id}",
        headers=student_headers,
    )
    assert unassign_response.status_code == 403


def test_rostered_teacher_cannot_assign_another_teachers_private_board(
    teacher_and_student, test_db_session
):
    teacher, student = teacher_and_student
    other_teacher = User(
        username="other_board_owner",
        password_hash=get_password_hash("StrongPass123"),
        display_name="Other Board Owner",
        user_type="teacher",
    )
    test_db_session.add(other_teacher)
    test_db_session.commit()

    other_teacher_headers = create_test_headers(
        other_teacher.id, other_teacher.username, other_teacher.user_type
    )
    teacher_headers = create_test_headers(teacher.id, teacher.username, teacher.user_type)
    board_response = client.post(
        "/api/boards/",
        json={"name": "Private board", "category": "general", "is_public": False},
        params={"user_id": other_teacher.id},
        headers=other_teacher_headers,
    )
    assert board_response.status_code == 200
    board_id = board_response.json()["id"]

    assign_response = client.post(
        f"/api/boards/{board_id}/assign",
        json={"student_id": student.id},
        headers=teacher_headers,
    )
    assert assign_response.status_code == 403
    assert (
        test_db_session.query(BoardAssignment)
        .filter_by(board_id=board_id, student_id=student.id)
        .count()
        == 0
    )

    test_db_session.add(
        BoardAssignment(board_id=board_id, student_id=student.id, assigned_by=other_teacher.id)
    )
    test_db_session.commit()
    unassign_response = client.delete(
        f"/api/boards/{board_id}/assign/{student.id}",
        headers=teacher_headers,
    )
    assert unassign_response.status_code == 403
    assert (
        test_db_session.query(BoardAssignment)
        .filter_by(board_id=board_id, student_id=student.id)
        .count()
        == 1
    )


def test_admin_can_manage_another_owners_board_assignment(
    teacher_and_student, test_db_session
):
    teacher, student = teacher_and_student
    admin = User(
        username="assignment_admin",
        password_hash=get_password_hash("StrongPass123"),
        display_name="Assignment Admin",
        user_type="admin",
    )
    owner = User(
        username="assignment_board_owner",
        password_hash=get_password_hash("StrongPass123"),
        display_name="Assignment Board Owner",
        user_type="teacher",
    )
    test_db_session.add_all([admin, owner])
    test_db_session.commit()

    owner_headers = create_test_headers(owner.id, owner.username, owner.user_type)
    admin_headers = create_test_headers(admin.id, admin.username, admin.user_type)
    board_response = client.post(
        "/api/boards/",
        json={"name": "Admin-managed board", "category": "general"},
        params={"user_id": owner.id},
        headers=owner_headers,
    )
    assert board_response.status_code == 200
    board_id = board_response.json()["id"]

    assert client.post(
        f"/api/boards/{board_id}/assign",
        json={"student_id": student.id},
        headers=admin_headers,
    ).status_code == 200
    assert (
        test_db_session.query(BoardAssignment)
        .filter_by(board_id=board_id, student_id=student.id)
        .count()
        == 1
    )
    assert client.delete(
        f"/api/boards/{board_id}/assign/{student.id}",
        headers=admin_headers,
    ).status_code == 200
    assert (
        test_db_session.query(BoardAssignment)
        .filter_by(board_id=board_id, student_id=student.id)
        .count()
        == 0
    )


def test_teacher_cannot_access_or_modify_unassigned_student(teacher_and_student, test_db_session):
    teacher, assigned_student = teacher_and_student
    other_student = User(
        username="student_other_assign",
        password_hash=get_password_hash("StrongPass123"),
        display_name="Other Student",
        user_type="student",
    )
    test_db_session.add(other_student)
    test_db_session.flush()
    test_db_session.add(
        StudentTeacher(student_id=assigned_student.id, teacher_id=teacher.id)
    )
    test_db_session.commit()

    teacher_headers = create_test_headers(teacher.id, teacher.username, teacher.user_type)
    create_response = client.post(
        "/api/boards/",
        json={"name": "Roster Board", "category": "general"},
        params={"user_id": teacher.id},
        headers=teacher_headers,
    )
    assert create_response.status_code == 200
    board_id = create_response.json()["id"]

    assigned_response = client.get(
        "/api/boards/assigned",
        params={"student_id": other_student.id},
        headers=teacher_headers,
    )
    assert assigned_response.status_code == 403

    assign_response = client.post(
        f"/api/boards/{board_id}/assign",
        json={"student_id": other_student.id},
        headers=teacher_headers,
    )
    assert assign_response.status_code == 403

    unassign_response = client.delete(
        f"/api/boards/{board_id}/assign/{other_student.id}",
        headers=teacher_headers,
    )
    assert unassign_response.status_code == 403
