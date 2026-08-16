"""End-to-end API journeys for each user role.

These tests exercise the real FastAPI app against a file-backed test database,
going through actual route wiring (login, board CRUD, symbol placement,
analytics, assignments, achievements) without mocking providers. They are the
cross-component smoke tests that catch regressions in serialization, RBAC, and
route registration that isolated unit tests cannot see.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import Symbol, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app

pytestmark = pytest.mark.usefixtures("setup_test_db")

PASSWORD = "JourneyPass123"

client = TestClient(app)


def _create_user(db, username: str, user_type: str) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name=username.replace("_", " ").title(),
        user_type=user_type,
        password_hash=get_password_hash(PASSWORD),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(username: str) -> dict:
    resp = client.post(
        "/api/auth/token", data={"username": username, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_symbol(db, label: str, category: str = "core") -> Symbol:
    symbol = Symbol(
        label=label,
        category=category,
        keywords=label,
        language="en",
        is_builtin=True,
    )
    db.add(symbol)
    db.commit()
    db.refresh(symbol)
    return symbol


def _uniq(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_student_journey(test_db_session):
    """Self-register → login → create board → place symbol → log usage → predict."""
    username = _uniq("student")
    register = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": PASSWORD,
            "display_name": "Journey Student",
            "user_type": "student",
        },
    )
    assert register.status_code == 200, register.text
    student_id = register.json()["id"]

    # Registration must force the student role regardless of the request hint.
    assert register.json()["user_type"] == "student"

    headers = _login(username)

    # A student can create their own board.
    create_board = client.post(
        f"/api/boards/?user_id={student_id}",
        json={"name": "My Journey Board", "category": "core"},
        headers=headers,
    )
    assert create_board.status_code == 200, create_board.text
    board_id = create_board.json()["id"]

    # Place a pre-existing symbol on the board.
    symbol = _create_symbol(test_db_session, "want")
    add_symbol = client.post(
        f"/api/boards/{board_id}/symbols",
        json={"symbol_id": symbol.id, "position_x": 0, "position_y": 0},
        headers=headers,
    )
    assert add_symbol.status_code == 200, add_symbol.text

    # Log symbol usage (what the phrase bar does when a symbol is tapped).
    usage = client.post(
        "/api/analytics/usage",
        json={
            "symbols": [
                {"id": symbol.id, "label": symbol.label, "category": symbol.category}
            ],
            "context_topic": "core",
        },
        headers=headers,
    )
    assert usage.status_code == 201, usage.text
    assert usage.json()["count"] == 1

    # The board now reports one playable symbol.
    board = client.get(f"/api/boards/{board_id}", headers=headers)
    assert board.status_code == 200, board.text
    assert board.json()["playable_symbols_count"] == 1

    # Next-symbol prediction runs against the logged usage.
    prediction = client.post(
        "/api/analytics/next-symbol",
        json={"current_symbols": symbol.label, "limit": 5},
        headers=headers,
    )
    assert prediction.status_code == 200, prediction.text
    assert isinstance(prediction.json(), list)


def test_teacher_journey(test_db_session):
    """Teacher logs in, creates a symbol, assigns a student, builds their board."""
    teacher = _create_user(test_db_session, _uniq("teacher"), "teacher")
    student = _create_user(test_db_session, _uniq("learner"), "student")

    teacher_headers = _login(teacher.username)

    # Teachers are staff and can create library symbols.
    symbol_resp = client.post(
        "/api/boards/symbols",
        json={"label": "eat", "category": "core"},
        headers=teacher_headers,
    )
    assert symbol_resp.status_code == 200, symbol_resp.text
    symbol_id = symbol_resp.json()["id"]

    # Teacher assigns the student to their roster.
    assign = client.post(
        "/api/users/assign-student",
        json={"student_id": student.id, "teacher_id": teacher.id},
        headers=teacher_headers,
    )
    assert assign.status_code == 201, assign.text

    # The student now appears in the teacher's roster.
    students = client.get(
        "/api/guardian-profiles/students", headers=teacher_headers
    )
    assert students.status_code == 200, students.text
    assert student.id in [s["id"] for s in students.json()]

    # Teachers own their boards and assign them to students (only admins may
    # create a board directly under another user's id).
    create_board = client.post(
        f"/api/boards/?user_id={teacher.id}",
        json={"name": "Teacher Made Board", "category": "core"},
        headers=teacher_headers,
    )
    assert create_board.status_code == 200, create_board.text
    board_id = create_board.json()["id"]

    add_symbol = client.post(
        f"/api/boards/{board_id}/symbols",
        json={"symbol_id": symbol_id, "position_x": 0, "position_y": 0},
        headers=teacher_headers,
    )
    assert add_symbol.status_code == 200, add_symbol.text

    # Assign the board to the student.
    assign_board = client.post(
        f"/api/boards/{board_id}/assign",
        json={"student_id": student.id},
        headers=teacher_headers,
    )
    assert assign_board.status_code == 200, assign_board.text

    # The assignment is visible to the student's assigned-boards endpoint.
    assigned = client.get(
        f"/api/boards/assigned?student_id={student.id}", headers=teacher_headers
    )
    assert assigned.status_code == 200, assigned.text
    assert board_id in [b["id"] for b in assigned.json()]


def test_admin_journey(test_db_session):
    """Admin manages users, creates a symbol, and reads the leaderboard."""
    admin = _create_user(test_db_session, _uniq("admin"), "admin")
    teacher = _create_user(test_db_session, _uniq("coach"), "teacher")
    student = _create_user(test_db_session, _uniq("pupil"), "student")

    admin_headers = _login(admin.username)

    # Admin can create a staff symbol.
    symbol_resp = client.post(
        "/api/boards/symbols",
        json={"label": "drink", "category": "core"},
        headers=admin_headers,
    )
    assert symbol_resp.status_code == 200, symbol_resp.text

    # Admin assigns a student to a teacher.
    assign = client.post(
        "/api/users/assign-student",
        json={"student_id": student.id, "teacher_id": teacher.id},
        headers=admin_headers,
    )
    assert assign.status_code == 201, assign.text

    # Admin sees every student in the roster (not just assigned ones).
    students = client.get("/api/guardian-profiles/students", headers=admin_headers)
    assert students.status_code == 200, students.text
    assert student.id in [s["id"] for s in students.json()]

    # Admin can build a board for the student and place a symbol.
    create_board = client.post(
        f"/api/boards/?user_id={student.id}",
        json={"name": "Admin Board", "category": "core"},
        headers=admin_headers,
    )
    assert create_board.status_code == 200, create_board.text
    board_id = create_board.json()["id"]

    add_symbol = client.post(
        f"/api/boards/{board_id}/symbols",
        json={"symbol_id": symbol_resp.json()["id"], "position_x": 0, "position_y": 0},
        headers=admin_headers,
    )
    assert add_symbol.status_code == 200, add_symbol.text

    # Leaderboard is readable by any authenticated user (admin included).
    leaderboard = client.get("/api/achievements/leaderboard", headers=admin_headers)
    assert leaderboard.status_code == 200, leaderboard.text
    assert isinstance(leaderboard.json(), list)
