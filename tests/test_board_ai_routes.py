"""Real-case API coverage for the AI board router (src/api/routers/board_ai.py).

Covers the permission/validation error paths of board creation, the AI
suggestions endpoints (success, unconfigured provider, offline fallback),
and the apply-suggestion flow (create vs. reuse symbol, duplicate cell).
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol, User
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)


@pytest.fixture
def ai_board(test_db_session: Session, admin_user: User) -> CommunicationBoard:
    """A board with AI enabled and a resolvable provider/model."""
    board = CommunicationBoard(
        user_id=admin_user.id,
        name="AI Suggestions Board",
        description="Generated content",
        grid_rows=4,
        grid_cols=5,
        ai_enabled=True,
        ai_provider="ollama",
        ai_model="test-model",
    )
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)
    return board


def test_non_admin_cannot_create_board_for_other_user(
    setup_test_db, test_db_session: Session, admin_user: User, user_token
):
    """A non-admin may only create boards for themselves (403)."""
    response = client.post(
        "/api/boards/",
        params={"user_id": admin_user.id},
        headers={"Authorization": f"Bearer {user_token}"},
        json={"name": "Sneaky board"},
    )
    assert response.status_code == 403


def test_admin_cannot_create_board_for_missing_user(
    setup_test_db, admin_user: User, admin_token
):
    """Creating a board for a nonexistent user returns 404."""
    response = client.post(
        "/api/boards/",
        params={"user_id": 999999},
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Ghost board"},
    )
    assert response.status_code == 404


def test_ai_board_requires_provider_and_model(
    setup_test_db, admin_user: User, admin_token
):
    """AI boards must specify provider and model (400)."""
    response = client.post(
        "/api/boards/",
        params={"user_id": admin_user.id},
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Half-configured AI board", "ai_enabled": True},
    )
    assert response.status_code == 400

    response = client.post(
        "/api/boards/",
        params={"user_id": admin_user.id},
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Bad provider AI board",
            "ai_enabled": True,
            "ai_provider": "chatgpt",
            "ai_model": "gpt-4",
        },
    )
    assert response.status_code == 400


def test_ai_board_generation_failure_aborts_creation(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """When AI generation fails, board creation is aborted with 502."""
    with patch("src.api.routers.board_ai.BoardGenerationService") as MockService:
        MockService.return_value.generate_board_items = AsyncMock(
            side_effect=RuntimeError("LLM unreachable")
        )
        with patch("src.api.routers.board_ai.OllamaProvider"):
            response = client.post(
                "/api/boards/",
                params={"user_id": admin_user.id},
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "name": "Doomed AI board",
                    "ai_enabled": True,
                    "ai_provider": "ollama",
                    "ai_model": "llama3",
                },
            )
    assert response.status_code == 502
    assert (
        test_db_session.query(CommunicationBoard)
        .filter_by(name="Doomed AI board")
        .count()
        == 0
    )


def test_suggestions_require_ai_enabled(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """Suggestions on a board without AI enabled return 400."""
    board = CommunicationBoard(
        user_id=admin_user.id, name="Plain board", ai_enabled=False
    )
    test_db_session.add(board)
    test_db_session.commit()

    response = client.post(
        f"/api/boards/{board.id}/ai/suggestions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"item_count": 3},
    )
    assert response.status_code == 400


def test_suggestions_unconfigured_provider_returns_400(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """A board with AI enabled but no resolvable model is not configured (400)."""
    board = CommunicationBoard(
        user_id=admin_user.id,
        name="Unconfigured AI board",
        ai_enabled=True,
        ai_provider="ollama",
        ai_model=None,
    )
    test_db_session.add(board)
    test_db_session.commit()

    response = client.post(
        f"/api/boards/{board.id}/ai/suggestions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"item_count": 3},
    )
    assert response.status_code == 400


def test_suggestions_success_with_mocked_generation(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """Successful suggestions return generated items without mutating the board."""
    items = [
        {"label": "Water", "symbol_key": "water"},
        {"label": "Hungry", "symbol_key": "hungry"},
    ]
    with patch(
        "src.api.routers.board_ai.BoardGenerationService.generate_board_items",
        new=AsyncMock(return_value=items),
    ):
        response = client.post(
            f"/api/boards/{ai_board.id}/ai/suggestions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"item_count": 2, "refine_prompt": "daily routine"},
        )
    assert response.status_code == 200
    assert response.json()["items"] == items
    # Suggestions must not create symbols on the board.
    assert test_db_session.query(BoardSymbol).count() == 0


def test_suggestions_offline_fallback_used_when_provider_fails(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """In non-production, a failing provider falls back to offline suggestions."""
    test_db_session.add_all(
        [
            Symbol(label="Cup", keywords="cup,drink", category="general"),
            Symbol(label="Walk", keywords="walk,outside", category="general"),
        ]
    )
    test_db_session.commit()

    with patch(
        "src.api.routers.board_ai.BoardGenerationService.generate_board_items",
        new=AsyncMock(side_effect=RuntimeError("timeout")),
    ):
        response = client.post(
            f"/api/boards/{ai_board.id}/ai/suggestions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"item_count": 2},
        )
    assert response.status_code == 200
    labels = {item["label"] for item in response.json()["items"]}
    assert labels == {"Cup", "Walk"}


def test_suggestions_502_when_no_offline_fallback_available(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """Without fallback symbols, a failing provider surfaces a 502."""
    with patch(
        "src.api.routers.board_ai.BoardGenerationService.generate_board_items",
        new=AsyncMock(side_effect=RuntimeError("timeout")),
    ):
        response = client.post(
            f"/api/boards/{ai_board.id}/ai/suggestions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"item_count": 2},
        )
    assert response.status_code == 502


def test_apply_suggestion_requires_ai_enabled(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    board = CommunicationBoard(
        user_id=admin_user.id, name="Plain board 2", ai_enabled=False
    )
    test_db_session.add(board)
    test_db_session.commit()

    response = client.post(
        f"/api/boards/{board.id}/ai/suggestions/apply",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"item": {"label": "Tea"}},
    )
    assert response.status_code == 400


def test_apply_suggestion_requires_label(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    response = client.post(
        f"/api/boards/{ai_board.id}/ai/suggestions/apply",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"item": {"symbol_key": "no_label"}},
    )
    # Missing label is rejected by schema validation before reaching the route.
    assert response.status_code == 422


def test_apply_suggestion_creates_and_reuses_symbol(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """Applying a suggestion creates the symbol, and re-applying reuses it."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    url = f"/api/boards/{ai_board.id}/ai/suggestions/apply"

    first = client.post(url, headers=headers, json={"item": {"label": "Pain"}})
    assert first.status_code == 200
    assert first.json()["custom_text"] == "Pain"

    # The symbol was created exactly once and placed on the board.
    symbols = test_db_session.query(Symbol).filter(Symbol.label == "Pain").all()
    assert len(symbols) == 1
    assert test_db_session.query(BoardSymbol).filter_by(board_id=ai_board.id).count() == 1

    # A second apply of the same label reuses the symbol and returns the same cell.
    second = client.post(url, headers=headers, json={"item": {"label": "Pain"}})
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert test_db_session.query(BoardSymbol).filter_by(board_id=ai_board.id).count() == 1


def test_apply_suggestion_uses_teacher_roster_access(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """A rostered teacher can apply suggestions to a student board."""
    from src.aac_app.models import StudentTeacher

    student = User(
        username="ai-roster-student",
        display_name="Roster Student",
        user_type="student",
        password_hash="test-hash",
        is_active=True,
    )
    teacher = User(
        username="ai-roster-teacher",
        display_name="Roster Teacher",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add_all([student, teacher])
    test_db_session.flush()

    board = CommunicationBoard(
        user_id=student.id,
        name="Student roster AI board",
        ai_enabled=True,
        ai_provider="ollama",
        ai_model="test-model",
    )
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add(StudentTeacher(teacher_id=teacher.id, student_id=student.id))
    test_db_session.commit()

    response = client.post(
        f"/api/boards/{board.id}/ai/suggestions/apply",
        headers=create_test_headers(teacher.id, teacher.username, teacher.user_type),
        json={"item": {"label": "Help", "color": "#FFCDD2"}},
    )
    assert response.status_code == 200
    assert response.json()["custom_text"] == "Help"
    assert response.json()["color"] == "#FFCDD2"
