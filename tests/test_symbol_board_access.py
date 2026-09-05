from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import BoardSymbol, CommunicationBoard, StudentTeacher, Symbol, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.auth_helpers import create_test_headers


def _user(db, username: str, user_type: str) -> User:
    user = User(
        username=username,
        display_name=username,
        user_type=user_type,
        password_hash=get_password_hash("TestPassword123"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _board(db, owner: User) -> tuple[CommunicationBoard, Symbol, BoardSymbol]:
    symbol = Symbol(label="Access symbol", category="general")
    board = CommunicationBoard(user_id=owner.id, name="Access board", category="general")
    db.add_all([symbol, board])
    db.flush()
    placement = BoardSymbol(board_id=board.id, symbol_id=symbol.id)
    db.add(placement)
    db.commit()
    db.refresh(placement)
    return board, symbol, placement


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("post", "/symbols", {"symbol_id": 1}),
        ("put", "/symbols/batch", [{"id": 1, "position_x": 1}]),
        ("put", "/symbols/1", {"position_x": 1}),
        ("delete", "/symbols/1", None),
    ],
)
def test_board_symbol_mutations_reject_non_owner(
    method, suffix, payload, setup_test_db, test_db_session
):
    owner = _user(test_db_session, "symbol_owner", "teacher")
    other = _user(test_db_session, "symbol_other", "teacher")
    board, symbol, placement = _board(test_db_session, owner)
    client = TestClient(app)
    url = f"/api/boards/{board.id}{suffix.replace('/1', f'/{placement.id}') }"
    request = getattr(client, method)
    kwargs = {"headers": create_test_headers(other.id, other.username, other.user_type)}
    if payload is not None and method in {"post", "put"}:
        body = dict(payload) if isinstance(payload, dict) else [dict(item) for item in payload]
        if method == "post":
            body["symbol_id"] = symbol.id
        kwargs["json"] = body
    response = request(url, **kwargs)
    assert response.status_code == 403


def test_rostered_teacher_can_view_private_student_board(
    setup_test_db, test_db_session
):
    teacher = _user(test_db_session, "detail_teacher", "teacher")
    student = _user(test_db_session, "detail_student", "student")
    test_db_session.add(StudentTeacher(teacher_id=teacher.id, student_id=student.id))
    board, _, _ = _board(test_db_session, student)
    test_db_session.commit()

    response = TestClient(app).get(
        f"/api/boards/{board.id}",
        headers=create_test_headers(teacher.id, teacher.username, teacher.user_type),
    )

    assert response.status_code == 200
    assert response.json()["id"] == board.id


def test_unrostered_teacher_cannot_view_private_student_board(
    setup_test_db, test_db_session
):
    owner = _user(test_db_session, "detail_owner", "student")
    teacher = _user(test_db_session, "detail_unrelated", "teacher")
    board, _, _ = _board(test_db_session, owner)

    response = TestClient(app).get(
        f"/api/boards/{board.id}",
        headers=create_test_headers(teacher.id, teacher.username, teacher.user_type),
    )

    assert response.status_code == 403



@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("post", "/symbols", {"symbol_id": 1}),
        ("put", "/symbols/batch", [{"id": 1, "position_x": 2}]),
        ("put", "/symbols/1", {"position_x": 2}),
        ("delete", "/symbols/1", None),
    ],
)
def test_board_symbol_mutations_return_404_for_missing_board(
    method, suffix, payload, setup_test_db, test_db_session, regular_user
):
    symbol = Symbol(label="Missing board symbol", category="general")
    test_db_session.add(symbol)
    test_db_session.commit()
    client = TestClient(app)
    url = f"/api/boards/999999{suffix.replace('/1', '/1')}"
    request = getattr(client, method)
    kwargs = {"headers": create_test_headers(regular_user.id, regular_user.username, regular_user.user_type)}
    if payload is not None:
        body = dict(payload) if isinstance(payload, dict) else [dict(item) for item in payload]
        if method == "post":
            body["symbol_id"] = symbol.id
        kwargs["json"] = body
    response = request(url, **kwargs)
    assert response.status_code == 404
