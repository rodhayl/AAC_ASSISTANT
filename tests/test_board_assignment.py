import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import User
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
    test_db_session.commit()
    return teacher, student


def test_board_assignment_flow(teacher_and_student):
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
