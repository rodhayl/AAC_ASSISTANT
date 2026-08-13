from fastapi.testclient import TestClient

from src.aac_app.models import (
    Achievement,
    BoardAssignment,
    BoardSymbol,
    CommunicationBoard,
    Symbol,
    User,
)
from src.api.main import app


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_board_with_symbol(test_db_session, admin_user):
    symbol = Symbol(
        label="Round-trip symbol",
        description="A symbol used to verify board placement serialization",
        category="general",
    )
    test_db_session.add(symbol)
    test_db_session.flush()

    board = CommunicationBoard(
        user_id=admin_user.id,
        name="Board with placement",
        description="Placement regression board",
        grid_rows=4,
        grid_cols=5,
    )
    test_db_session.add(board)
    test_db_session.flush()

    board_symbol = BoardSymbol(
        board_id=board.id,
        symbol_id=symbol.id,
        position_x=2,
        position_y=3,
        custom_text="Use this label",
        is_visible=True,
    )
    test_db_session.add(board_symbol)
    test_db_session.commit()
    test_db_session.refresh(board)
    return board


def test_board_list_includes_positioned_symbols(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = _create_board_with_symbol(test_db_session, admin_user)
    client = TestClient(app)

    response = client.get("/api/boards/", headers=_headers(admin_token))

    assert response.status_code == 200
    listed_board = next(item for item in response.json() if item["id"] == board.id)
    assert listed_board["symbols"] == [
        {
            "id": board.symbols[0].id,
            "symbol_id": board.symbols[0].symbol_id,
            "position_x": 2,
            "position_y": 3,
            "size": 1,
            "is_visible": True,
            "custom_text": "Use this label",
            "color": None,
            "linked_board_id": None,
            "symbol": {
                "id": board.symbols[0].symbol.id,
                "label": "Round-trip symbol",
                "description": "A symbol used to verify board placement serialization",
                "category": "general",
                "image_path": None,
                "audio_path": None,
                "keywords": None,
                "language": "en",
                "is_builtin": False,
                "created_at": board.symbols[0].symbol.created_at.isoformat(),
            },
        }
    ]


def test_delete_board_removes_assignments(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = CommunicationBoard(
        user_id=admin_user.id,
        name="Assigned board",
        description="Assignment deletion regression",
    )
    test_db_session.add(board)
    test_db_session.flush()

    student = User(
        username="board-delete-student",
        display_name="Board Delete Student",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.flush()
    assignment = BoardAssignment(board_id=board.id, student_id=student.id)
    test_db_session.add(assignment)
    test_db_session.commit()

    client = TestClient(app)
    response = client.delete(f"/api/boards/{board.id}", headers=_headers(admin_token))

    assert response.status_code == 200
    assert test_db_session.query(BoardAssignment).filter_by(board_id=board.id).count() == 0


def test_delete_board_clears_incoming_links(
    setup_test_db, test_db_session, admin_user, admin_token
):
    target = CommunicationBoard(
        user_id=admin_user.id,
        name="Linked target",
        description="Incoming link target",
    )
    source = CommunicationBoard(
        user_id=admin_user.id,
        name="Linked source",
        description="Incoming link source",
    )
    test_db_session.add_all([target, source])
    test_db_session.flush()
    symbol = Symbol(label="Linked symbol", category="general")
    test_db_session.add(symbol)
    test_db_session.flush()
    placement = BoardSymbol(
        board_id=source.id,
        symbol_id=symbol.id,
        linked_board_id=target.id,
    )
    test_db_session.add(placement)
    test_db_session.commit()

    client = TestClient(app)
    response = client.delete(f"/api/boards/{target.id}", headers=_headers(admin_token))

    assert response.status_code == 200
    test_db_session.refresh(placement)
    assert placement.linked_board_id is None


def test_export_delete_import_round_trip_lists_restored_symbols(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = _create_board_with_symbol(test_db_session, admin_user)
    client = TestClient(app)
    headers = _headers(admin_token)

    exported = client.get(
        "/api/data/export",
        params={"username": admin_user.username},
        headers=headers,
    )
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["boards"][0]["symbols"][0]["position_x"] == 2
    assert payload["boards"][0]["symbols"][0]["custom_text"] == "Use this label"

    deleted = client.delete(f"/api/boards/{board.id}", headers=headers)
    assert deleted.status_code == 200

    imported = client.post("/api/data/import", json=payload, headers=headers)
    assert imported.status_code == 200

    listed = client.get("/api/boards/", headers=headers)
    assert listed.status_code == 200
    restored = next(item for item in listed.json() if item["name"] == board.name)
    assert len(restored["symbols"]) == 1
    assert restored["symbols"][0]["position_x"] == 2
    assert restored["symbols"][0]["position_y"] == 3
    assert restored["symbols"][0]["custom_text"] == "Use this label"


def test_import_restores_assigned_board_relationship(
    setup_test_db, test_db_session, admin_user, admin_token
):
    student = User(
        username="assigned-import-student",
        display_name="Assigned Import Student",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.flush()
    board = CommunicationBoard(
        user_id=admin_user.id,
        name="Assigned import board",
        description="Assignment round-trip",
    )
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add(BoardAssignment(board_id=board.id, student_id=student.id))
    test_db_session.commit()

    client = TestClient(app)
    payload = client.get(
        "/api/data/export",
        params={"username": student.username},
        headers=_headers(admin_token),
    )
    assert payload.status_code == 200
    export = payload.json()
    assert [item["id"] for item in export["assignedBoards"]] == [board.id]

    imported = client.post(
        "/api/data/import",
        json=export,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert imported.status_code == 200
    restored_board = (
        test_db_session.query(CommunicationBoard)
        .filter(
            CommunicationBoard.user_id == student.id,
            CommunicationBoard.name == board.name,
        )
        .one()
    )
    assert (
        test_db_session.query(BoardAssignment)
        .filter_by(board_id=restored_board.id, student_id=student.id)
        .count()
        == 1
    )


def test_achievements_list_and_create_accept_both_slash_variants(
    setup_test_db, test_db_session, admin_user, admin_token
):
    test_db_session.add(
        Achievement(
            name="Seeded achievement",
            description="Visible in the management list",
            category="general",
            is_active=True,
        )
    )
    test_db_session.commit()
    client = TestClient(app)
    headers = _headers(admin_token)

    for path in ("/api/achievements", "/api/achievements/"):
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert any(item["name"] == "Seeded achievement" for item in response.json())

    for path, name in (
        ("/api/achievements", "Created without slash"),
        ("/api/achievements/", "Created with slash"),
    ):
        response = client.post(
            path,
            headers=headers,
            json={
                "name": name,
                "description": "Route regression",
                "category": "custom",
                "points": 5,
            },
        )
        assert response.status_code == 201
        assert response.json()["name"] == name
