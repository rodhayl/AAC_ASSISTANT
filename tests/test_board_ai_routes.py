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


def test_update_board_rejects_invalid_ai_provider(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """Updating a board with AI enabled must reject an unsupported provider (400)."""
    board = CommunicationBoard(
        user_id=admin_user.id, name="Plain board", ai_enabled=False
    )
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    response = client.put(
        f"/api/boards/{board.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "ai_enabled": True,
            "ai_provider": "unsupported-provider",
            "ai_model": "local-model",
        },
    )
    assert response.status_code == 400

    # The invalid provider must not have been persisted.
    test_db_session.refresh(board)
    assert board.ai_provider != "unsupported-provider"
    assert board.ai_enabled is False


def test_disabled_board_still_rejects_invalid_ai_provider(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """A disabled board must not persist an unsupported provider value."""
    response = client.post(
        "/api/boards/",
        params={"user_id": admin_user.id},
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Invalid disabled provider",
            "ai_enabled": False,
            "ai_provider": "unsupported-provider",
        },
    )
    assert response.status_code == 400


def test_update_disabled_board_rejects_invalid_ai_provider(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """Disabling AI must not make invalid provider metadata acceptable."""
    board = CommunicationBoard(
        user_id=admin_user.id, name="Plain board", ai_enabled=False
    )
    test_db_session.add(board)
    test_db_session.commit()

    response = client.put(
        f"/api/boards/{board.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"ai_provider": "unsupported-provider"},
    )
    assert response.status_code == 400


def test_lmstudio_board_generation_is_supported(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """LM Studio can be selected for AI boards just like other providers."""
    with (
        patch("src.api.routers.board_ai.BoardGenerationService") as mock_service,
        patch("src.api.routers.board_ai.LMStudioProvider") as mock_provider,
    ):
        mock_service.return_value.generate_board_items = AsyncMock(
            return_value=[
                {"label": "Local item", "symbol_key": "local_item", "color": "#FFFFFF"}
            ]
        )
        response = client.post(
            "/api/boards/",
            params={"user_id": admin_user.id},
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "LM Studio board",
                "ai_enabled": True,
                "ai_provider": "lmstudio",
                "ai_model": "local-model",
            },
        )

    assert response.status_code == 200
    assert response.json()["ai_provider"] == "lmstudio"
    mock_provider.assert_called_once()


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


def test_suggestions_fail_explicitly_when_provider_fails(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """A provider failure is surfaced instead of replaced by offline suggestions."""
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
    assert response.status_code == 502
    detail = response.json()["detail"]
    # The exception is logged server-side; the client sees only the safe
    # exception-class label, never the raw message.
    assert "RuntimeError" in detail
    assert "timeout" not in detail


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


def test_apply_suggestion_replaces_occupant_at_explicit_position(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """An explicit position replaces the occupying symbol atomically."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    url = f"/api/boards/{ai_board.id}/ai/suggestions/apply"

    first = client.post(
        url,
        headers=headers,
        json={"item": {"label": "Old"}, "position_x": 1, "position_y": 2},
    )
    assert first.status_code == 200
    old_id = first.json()["id"]

    # Replacing at the same explicit position must swap the occupant in one
    # transaction: the new symbol lands there and the old placement is gone.
    second = client.post(
        url,
        headers=headers,
        json={"item": {"label": "New"}, "position_x": 1, "position_y": 2},
    )
    assert second.status_code == 200
    assert second.json()["position_x"] == 1
    assert second.json()["position_y"] == 2
    assert second.json()["id"] != old_id

    placements = test_db_session.query(BoardSymbol).filter_by(
        board_id=ai_board.id
    ).all()
    assert len(placements) == 1
    assert placements[0].custom_text == "New"


def test_apply_suggestion_auto_places_when_position_omitted(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """Adding without coordinates keeps auto-placing at the first free cell."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    url = f"/api/boards/{ai_board.id}/ai/suggestions/apply"

    # Occupy the (0, 0) default target.
    first = client.post(url, headers=headers, json={"item": {"label": "First"}})
    assert first.status_code == 200
    assert (first.json()["position_x"], first.json()["position_y"]) == (0, 0)

    # A second add without coordinates must move to the next free cell
    # (scanned column-major), not replace (0, 0).
    second = client.post(url, headers=headers, json={"item": {"label": "Second"}})
    assert second.status_code == 200
    assert (second.json()["position_x"], second.json()["position_y"]) == (1, 0)
    assert test_db_session.query(BoardSymbol).filter_by(
        board_id=ai_board.id
    ).count() == 2


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


def test_create_board_schedules_download_for_generated_symbols(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """AI board creation schedules an image download for newly created symbols."""
    items = [{"label": "Apple", "symbol_key": "apple", "color": "#FFCDD2"}]
    with patch("src.api.routers.board_ai.BoardGenerationService") as MockService:
        MockService.return_value.generate_board_items = AsyncMock(return_value=items)
        with patch("src.api.routers.board_ai.OllamaProvider"), patch(
            "src.api.routers.board_ai.schedule_symbol_image_download"
        ) as mock_schedule:
            response = client.post(
                "/api/boards/",
                params={"user_id": admin_user.id},
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "name": "Schedule Test Board",
                    "ai_enabled": True,
                    "ai_provider": "ollama",
                    "ai_model": "llama3",
                },
            )
    assert response.status_code == 200
    symbol = test_db_session.query(Symbol).filter(Symbol.label == "Apple").one()
    # No dead /static placeholder; the image is filled by the scheduled download.
    assert symbol.image_path is None
    mock_schedule.assert_called_once_with([symbol.id])


def test_create_board_with_primary_marker_resolves_global_model(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token
):
    """A board created with ai_model='@primary' uses the global primary model."""
    items = [{"label": "Apple", "symbol_key": "apple", "color": "#FFCDD2"}]
    with (
        patch("src.api.routers.board_ai.BoardGenerationService") as mock_service,
        patch("src.api.routers.board_ai.OllamaProvider") as mock_provider,
        patch(
            "src.api.routers.board_ai.get_setting_value",
            side_effect=lambda key, default="": (
                "http://ollama.test"
                if key == "ollama_base_url"
                else "global-ollama-model"
                if key == "ollama_model"
                else default
            ),
        ) as mock_setting,
    ):
        mock_service.return_value.generate_board_items = AsyncMock(return_value=items)
        response = client.post(
            "/api/boards/",
            params={"user_id": admin_user.id},
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Primary Marker Board",
                "ai_enabled": True,
                "ai_provider": "ollama",
                "ai_model": "@primary",
            },
        )
    assert response.status_code == 200
    # The provider must receive the resolved global model, never the marker.
    mock_provider.assert_called_once_with(
        base_url="http://ollama.test", model="global-ollama-model"
    )
    mock_setting.assert_any_call("ollama_model", "")


def test_apply_suggestion_schedules_download_only_when_symbol_created(
    setup_test_db, test_db_session: Session, admin_user: User, admin_token, ai_board
):
    """Applying a suggestion downloads once on create and not on reuse."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    url = f"/api/boards/{ai_board.id}/ai/suggestions/apply"

    with patch(
        "src.api.routers.board_ai.schedule_symbol_image_download"
    ) as mock_schedule:
        first = client.post(url, headers=headers, json={"item": {"label": "Fresh"}})
        assert first.status_code == 200
        created_id = mock_schedule.call_args.args[0][0]
        mock_schedule.assert_called_once_with([created_id])

    with patch(
        "src.api.routers.board_ai.schedule_symbol_image_download"
    ) as mock_schedule:
        second = client.post(url, headers=headers, json={"item": {"label": "Fresh"}})
        assert second.status_code == 200
        mock_schedule.assert_not_called()

    symbol = test_db_session.query(Symbol).filter(Symbol.label == "Fresh").one()
    assert symbol.image_path is None
