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


def test_delete_board_removes_own_placements_keeps_symbol(
    setup_test_db, test_db_session, admin_user, admin_token
):
    """Deleting a board removes its placements but keeps the global symbol."""
    board = _create_board_with_symbol(test_db_session, admin_user)
    symbol_id = board.symbols[0].symbol_id
    placement_id = board.symbols[0].id

    client = TestClient(app)
    response = client.delete(f"/api/boards/{board.id}", headers=_headers(admin_token))

    assert response.status_code == 200
    # Use count queries so the identity map does not mask cross-session deletes.
    assert test_db_session.query(BoardSymbol).filter_by(id=placement_id).count() == 0
    assert (
        test_db_session.query(CommunicationBoard).filter_by(id=board.id).count() == 0
    )
    # The symbol is shared library state, not owned by the board.
    assert test_db_session.query(Symbol).filter_by(id=symbol_id).count() == 1


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


def test_board_links_reject_self_and_missing_targets(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = _create_board_with_symbol(test_db_session, admin_user)
    client = TestClient(app)
    headers = _headers(admin_token)
    symbol_id = board.symbols[0].symbol_id

    self_link = client.post(
        f"/api/boards/{board.id}/symbols",
        json={"symbol_id": symbol_id, "linked_board_id": board.id},
        headers=headers,
    )
    assert self_link.status_code == 400

    existing_symbol_id = board.symbols[0].id
    missing_target = client.put(
        f"/api/boards/{board.id}/symbols/{existing_symbol_id}",
        json={"linked_board_id": 999999999},
        headers=headers,
    )
    assert missing_target.status_code == 404

    unchanged = test_db_session.get(BoardSymbol, existing_symbol_id)
    assert unchanged is not None
    assert unchanged.linked_board_id is None


def test_batch_board_symbol_updates_validate_payload_and_apply_color(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = _create_board_with_symbol(test_db_session, admin_user)
    replacement = Symbol(label="Replacement symbol", category="general")
    test_db_session.add(replacement)
    test_db_session.commit()
    placement = board.symbols[0]

    client = TestClient(app)
    response = client.put(
        f"/api/boards/{board.id}/symbols/batch",
        headers=_headers(admin_token),
        json=[
            {
                "id": placement.id,
                "symbol_id": replacement.id,
                "position_x": 1,
                "position_y": 1,
                "color": "#123456",
            }
        ],
    )

    assert response.status_code == 200
    test_db_session.expire_all()
    updated = test_db_session.get(BoardSymbol, placement.id)
    assert updated is not None
    assert updated.symbol_id == replacement.id
    assert updated.position_x == 1
    assert updated.position_y == 1
    assert updated.color == "#123456"


def test_batch_board_symbol_updates_reject_invalid_position_without_partial_write(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = _create_board_with_symbol(test_db_session, admin_user)
    placement = board.symbols[0]
    client = TestClient(app)

    response = client.put(
        f"/api/boards/{board.id}/symbols/batch",
        headers=_headers(admin_token),
        json=[{"id": placement.id, "position_x": -1}],
    )

    assert response.status_code == 422
    test_db_session.expire_all()
    unchanged = test_db_session.get(BoardSymbol, placement.id)
    assert unchanged is not None
    assert unchanged.position_x == 2


def test_board_mutations_reject_invalid_grid_positions_and_preserve_layout(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = _create_board_with_symbol(test_db_session, admin_user)
    client = TestClient(app)
    headers = _headers(admin_token)

    out_of_bounds = client.post(
        f"/api/boards/{board.id}/symbols",
        headers=headers,
        json={
            "symbol_id": board.symbols[0].symbol_id,
            "position_x": 5,
            "position_y": 0,
        },
    )
    assert out_of_bounds.status_code == 400
    assert "position" in out_of_bounds.json()["detail"].lower()

    shrink = client.put(
        f"/api/boards/{board.id}",
        headers=headers,
        json={"grid_rows": 2, "grid_cols": 2},
    )
    assert shrink.status_code == 400
    test_db_session.expire_all()
    persisted = test_db_session.get(CommunicationBoard, board.id)
    assert (persisted.grid_rows, persisted.grid_cols) == (4, 5)


def test_board_create_rejects_invalid_manual_symbols_atomically(
    setup_test_db, test_db_session, admin_user, admin_token
):
    symbol = Symbol(label="Valid manual symbol", category="general")
    test_db_session.add(symbol)
    test_db_session.commit()
    client = TestClient(app)
    headers = _headers(admin_token)

    invalid_symbol = client.post(
        "/api/boards/",
        params={"user_id": admin_user.id},
        headers=headers,
        json={
            "name": "Invalid symbol board",
            "symbols": [{"symbol_id": 999999999, "position_x": 0, "position_y": 0}],
        },
    )
    assert invalid_symbol.status_code == 404
    assert test_db_session.query(CommunicationBoard).filter_by(name="Invalid symbol board").count() == 0

    invalid_link = client.post(
        "/api/boards/",
        params={"user_id": admin_user.id},
        headers=headers,
        json={
            "name": "Invalid link board",
            "symbols": [{"symbol_id": symbol.id, "linked_board_id": 999999999}],
        },
    )
    assert invalid_link.status_code == 404
    assert test_db_session.query(CommunicationBoard).filter_by(name="Invalid link board").count() == 0


def test_ai_suggestion_on_full_board_returns_localized_error(
    setup_test_db, test_db_session, admin_user, admin_token
):
    board = CommunicationBoard(
        user_id=admin_user.id,
        name="Full AI board",
        description="A one-cell board for error handling",
        grid_rows=1,
        grid_cols=1,
        ai_enabled=True,
        ai_provider="ollama",
        ai_model="test-model",
    )
    symbol = Symbol(label="Existing cell", category="general")
    test_db_session.add_all([board, symbol])
    test_db_session.flush()
    test_db_session.add(
        BoardSymbol(board_id=board.id, symbol_id=symbol.id, position_x=0, position_y=0)
    )
    test_db_session.commit()

    client = TestClient(app)
    response = client.post(
        f"/api/boards/{board.id}/ai/suggestions/apply",
        headers=_headers(admin_token),
        json={"item": {"label": "Another cell", "symbol_key": "another_cell"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] != "errors.boards.boardFull"
    assert "board" in response.json()["detail"].lower()


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


def test_board_list_name_filter_matches_literally(
    setup_test_db, test_db_session, admin_user, admin_token
):
    """Board-name search treats % and _ as literal text, not LIKE wildcards."""
    client = TestClient(app)
    names = ["100%_sure", "dog house", "100%"]
    boards = [
        CommunicationBoard(
            user_id=admin_user.id,
            name=name,
            grid_rows=2,
            grid_cols=2,
        )
        for name in names
    ]
    test_db_session.add_all(boards)
    test_db_session.commit()

    def search(term: str) -> set[str]:
        response = client.get(
            "/api/boards/", params={"name": term}, headers=_headers(admin_token)
        )
        assert response.status_code == 200
        return {item["name"] for item in response.json()}

    # A lone "%" must not list every board: it matches only literal percent.
    assert search("%") == {"100%_sure", "100%"}
    # "_" is a literal underscore, not a single-character wildcard: no board
    # name spells d_g, so the search is empty (it must not match "dog house").
    assert search("d_g") == set()
    assert search("100%") == {"100%_sure", "100%"}
    assert search("dog") == {"dog house"}
