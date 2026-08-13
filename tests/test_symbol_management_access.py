import io

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import Symbol, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("setup_test_db")


def test_students_can_read_but_not_mutate_global_symbol_library(admin_user, test_db_session):
    student = User(
        username="symbol_read_only_student",
        display_name="Symbol Read Only Student",
        password_hash=get_password_hash("StudentPass123"),
        user_type="student",
    )
    teacher = User(
        username="symbol_management_teacher",
        display_name="Symbol Management Teacher",
        password_hash=get_password_hash("TeacherPass123"),
        user_type="teacher",
    )
    test_db_session.add_all([student, teacher])
    test_db_session.commit()
    test_db_session.refresh(student)
    test_db_session.refresh(teacher)

    admin_headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    teacher_headers = create_test_headers(teacher.id, teacher.username, "teacher")
    student_headers = create_test_headers(student.id, student.username, "student")

    created = client.post(
        "/api/boards/symbols",
        json={"label": "Staff Symbol", "category": "test"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    symbol_id = created.json()["id"]

    teacher_reorder = client.put(
        "/api/boards/symbols/reorder",
        json=[{"id": symbol_id, "order_index": 7}],
        headers=teacher_headers,
    )
    assert teacher_reorder.status_code == 200, teacher_reorder.text
    assert teacher_reorder.json() == {"ok": True, "updated": 1}

    readable = client.get("/api/boards/symbols", headers=student_headers)
    assert readable.status_code == 200
    assert any(item["id"] == symbol_id for item in readable.json())

    assert client.post(
        "/api/boards/symbols",
        json={"label": "Forbidden Symbol", "category": "test"},
        headers=student_headers,
    ).status_code == 403
    assert client.put(
        "/api/boards/symbols/reorder",
        json=[{"id": symbol_id, "order_index": 99}],
        headers=student_headers,
    ).status_code == 403
    assert client.put(
        f"/api/boards/symbols/{symbol_id}",
        json={"label": "Forbidden Update"},
        headers=student_headers,
    ).status_code == 403
    assert client.post(
        "/api/boards/symbols/upload",
        data={"label": "Forbidden Upload", "category": "test"},
        files={"file": ("symbol.png", io.BytesIO(b"not-an-image"), "image/png")},
        headers=student_headers,
    ).status_code == 403
    assert client.delete(
        f"/api/boards/symbols/{symbol_id}",
        headers=student_headers,
    ).status_code == 403

    persisted = test_db_session.query(Symbol).filter(Symbol.id == symbol_id).one()
    assert persisted.label == "Staff Symbol"
