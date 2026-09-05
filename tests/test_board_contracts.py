"""Contract tests pinning backend response shapes consumed by the frontend.

These exist so the backend↔frontend contracts audited by hand are enforced
mechanically instead of "verified by eye":
- serialize_board never emits ``symbol: null`` for a persisted placement
  (the TS ``BoardSymbol.symbol`` type is non-nullable);
- the ``/users/assign-student`` idempotency payload is exactly
  ``{message, status}`` with ``status in {"created", "exists"}``;
- the LM Studio model-listing divergence (compat route returns 200 with an
  ``error`` key, canonical route raises 503) is intentional and pinned;
- symbol image upload errors map to the i18n keys the frontend surfaces
  (``errors.boards.invalidFileType`` / ``fileTooLarge`` / ``emptyFile``);
- the SSE notification stream payload matches the frontend
  ``NotificationItem`` interface exactly (8 keys, ISO timestamps);
- ``POST /learning/start`` (success) returns exactly the keys the TS
  ``LearningSessionResponse`` interface declares (incl. ``provider_used``).
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from src.api.routers.board_helpers import serialize_board
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


def _make_board_with_symbol(db, admin: User) -> tuple[CommunicationBoard, BoardSymbol]:
    symbol = Symbol(label="contract_label", language="en")
    db.add(symbol)
    db.flush()
    board = CommunicationBoard(
        user_id=admin.id, name="Contract Board", grid_rows=2, grid_cols=2
    )
    db.add(board)
    db.flush()
    placement = BoardSymbol(
        board_id=board.id, symbol_id=symbol.id, position_x=0, position_y=0
    )
    db.add(placement)
    db.commit()
    db.refresh(board)
    db.refresh(placement)
    return board, placement


def test_serialize_board_symbol_is_never_null(test_db_session, admin_user):
    """A persisted placement with a valid symbol_id serializes a full symbol."""
    board, placement = _make_board_with_symbol(test_db_session, admin_user)
    assert placement.symbol is not None

    serialized = serialize_board(board)
    assert serialized["symbols"], "expected at least one placement"
    for entry in serialized["symbols"]:
        assert entry["symbol"] is not None
        assert set(entry["symbol"]) >= {
            "id",
            "label",
            "category",
            "image_path",
            "audio_path",
            "keywords",
            "language",
            "is_builtin",
            "created_at",
        }


def test_board_response_symbol_is_never_null_over_http(
    test_db_session, admin_user, admin_token, client: TestClient
):
    """GET /api/boards/{id} never returns symbol: null inside placements."""
    board, _ = _make_board_with_symbol(test_db_session, admin_user)
    response = client.get(
        f"/api/boards/{board.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbols"], "expected at least one placement"
    for entry in payload["symbols"]:
        assert isinstance(entry["symbol"], dict)


@pytest.fixture
def teacher_user(test_db_session):
    user = User(
        username="contract_teacher",
        display_name="Contract Teacher",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def student_user(test_db_session):
    user = User(
        username="contract_student",
        display_name="Contract Student",
        user_type="student",
        password_hash=get_password_hash("StudentPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


def test_assign_student_contract_shape(teacher_user, student_user):
    """The assign-student payload is exactly {message, status}."""
    headers = create_test_headers(
        teacher_user.id, teacher_user.username, "teacher"
    )
    payload = {"student_id": student_user.id, "teacher_id": teacher_user.id}

    created = client.post(
        "/api/users/assign-student", headers=headers, json=payload
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"message", "status"}
    assert body["status"] == "created"
    assert body["message"]

    repeat = client.post(
        "/api/users/assign-student", headers=headers, json=payload
    )
    assert repeat.status_code == 200
    body = repeat.json()
    assert set(body) == {"message", "status"}
    assert body["status"] == "exists"


def test_lmstudio_model_listing_divergence_is_intentional(
    admin_user, admin_token, monkeypatch
):
    """Pin the two LM Studio routes as deliberately different.

    ``/api/providers/ai/models/lmstudio`` is a legacy compatibility route:
    older clients expect HTTP 200 with ``{"models": [], "error": ...}`` rather
    than an HTTP error status. ``/api/settings/ai/models/lmstudio`` is the
    canonical admin route and surfaces unavailability as 503. Do not
    "unify" them without re-checking BACKEND_CHANGE_VALIDATION_MATRIX.md
    (CHG-04): deleting the compat route already broke external callers once.
    """
    from unittest.mock import MagicMock

    unavailable = MagicMock()
    unavailable.is_available.return_value = False
    monkeypatch.setattr(
        "src.api.routers.providers.get_lmstudio_provider", lambda: unavailable
    )

    compat = client.get(
        "/api/providers/ai/models/lmstudio",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert compat.status_code == 200
    assert compat.json() == {"models": [], "error": "LM Studio is not available"}

    monkeypatch.setattr(
        "src.api.routers.settings.LMStudioProvider", lambda **kwargs: unavailable
    )
    canonical = client.get(
        "/api/settings/ai/models/lmstudio",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert canonical.status_code == 503


def test_symbol_upload_error_details_use_frontend_i18n_keys(
    test_db_session, admin_user, admin_token, client: TestClient
):
    """Upload rejections carry the exact i18n strings the frontend shows.

    The frontend surfaces ``errors.boards.invalidFileType`` /
    ``fileTooLarge`` / ``emptyFile`` from its locale files; the backend must
    produce byte-identical details so the UI and API errors agree.
    """
    from src.aac_app.services.translation_service import (
        get_translation_service,
    )

    translation_service = get_translation_service()

    expected = {
        key: translation_service.get("en", "common", f"errors.boards.{key}")
        for key in ("invalidFileType", "fileTooLarge", "emptyFile")
    }
    assert all(expected.values()), "i18n keys must exist in en"
    auth = {"Authorization": f"Bearer {admin_token}"}
    form = {
        "label": "contract upload",
        "category": "general",
        "language": "en",
    }

    # Empty file -> emptyFile.
    response = client.post(
        "/api/boards/symbols/upload",
        headers=auth,
        data=form,
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == expected["emptyFile"]

    # Wrong content type (text masquerading as an image) -> invalidFileType.
    response = client.post(
        "/api/boards/symbols/upload",
        headers=auth,
        data=form,
        files={"file": ("fake.png", b"definitely not an image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == expected["invalidFileType"]

    # Declared type text/plain -> invalidFileType (rejected before read).
    response = client.post(
        "/api/boards/symbols/upload",
        headers=auth,
        data=form,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == expected["invalidFileType"]

    # Oversized image (>5MB) -> fileTooLarge (413).
    big = Image.new("RGB", (32, 32), "red")
    buffer = io.BytesIO()
    big.save(buffer, format="PNG")
    response = client.post(
        "/api/boards/symbols/upload",
        headers=auth,
        data=form,
        files={"file": ("big.png", buffer.getvalue() + b"\0" * (5 * 1024 * 1024 + 1), "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == expected["fileTooLarge"]


def test_notification_sse_payload_matches_frontend_notification_item(
    test_db_session, admin_user, regular_user, admin_token, client: TestClient
):
    """The SSE event payload has exactly the 8 NotificationItem keys.

    The frontend ``NotificationItem`` interface declares id/title/message/
    type/priority/is_read/created_at/read_at with ISO-8601 timestamps; the
    stream must never add, drop, or rename a key.
    """
    from datetime import datetime

    from src.aac_app.models import Notification
    from src.aac_app.services.notification_events import (
        notification_payload,
    )

    notification = Notification(
        user_id=regular_user.id,
        title="Contract",
        message="Payload shape",
        notification_type="info",
        priority="normal",
        is_read=False,
        created_at=datetime(2026, 9, 4, 12, 0, 0),
        read_at=None,
    )
    test_db_session.add(notification)
    test_db_session.commit()
    test_db_session.refresh(notification)

    payload = notification_payload(notification)
    assert set(payload) == {
        "id",
        "title",
        "message",
        "type",
        "priority",
        "is_read",
        "created_at",
        "read_at",
    }
    # Timestamps must be ISO strings the frontend can new Date() directly.
    from datetime import datetime as dt

    dt.fromisoformat(payload["created_at"])
    assert payload["read_at"] is None
    assert payload["is_read"] is False
    assert payload["type"] == "info"


def test_auth_token_and_refresh_payloads_match_frontend_authstore(
    test_db_session, admin_user, admin_token, client: TestClient
):
    """Token + refresh responses expose exactly the keys authStore reads.

    ``authStore.login`` reads ``access_token``/``refresh_token`` off
    ``POST /auth/token``; ``refreshAccessToken`` reads ``access_token``
    (and nothing else) off ``POST /auth/refresh``. An added or renamed key
    is a silent frontend contract change.
    """
    from src.aac_app.services.auth_service import get_password_hash

    user = User(
        username="contract_token_user",
        display_name="Contract Token User",
        user_type="student",
        password_hash=get_password_hash("ContractPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    login = client.post(
        "/api/auth/token",
        data={"username": "contract_token_user", "password": "ContractPass123"},
    )
    assert login.status_code == 200, login.text
    login_body = login.json()
    assert set(login_body) == {"access_token", "token_type", "refresh_token"}
    assert login_body["token_type"] == "bearer"

    refresh = client.post(
        "/api/auth/refresh",
        params={"refresh_token": login_body["refresh_token"]},
    )
    assert refresh.status_code == 200, refresh.text
    # The frontend refresh handler consumes exactly access_token + token_type.
    assert set(refresh.json()) == {"access_token", "token_type"}
    assert refresh.json()["token_type"] == "bearer"


def test_board_ai_suggestions_contract_matches_frontend_type(
    test_db_session, admin_user, admin_token, client: TestClient
):
    """POST /boards/{id}/ai/suggestions returns exactly {items} with the
    keys the frontend ``AISuggestion`` type (components/board/
    AISuggestionPanel.tsx) consumes: label/symbol_key/color/description;
    ``linked_board_id`` is backend-only and must never be renamed or dropped
    when present.
    """
    from unittest.mock import AsyncMock, patch

    board = CommunicationBoard(
        user_id=admin_user.id,
        name="AI contract board",
        grid_rows=4,
        grid_cols=5,
        ai_enabled=True,
        ai_provider="ollama",
        ai_model="test-model",
    )
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    items = [
        {
            "label": "Water",
            "symbol_key": "water",
            "color": "#3B82F6",
            "linked_board_id": None,
            "description": "a drink",
        },
        {"label": "Hungry", "symbol_key": "hungry"},
    ]
    with patch(
        "src.api.routers.board_ai.BoardGenerationService.generate_board_items",
        new=AsyncMock(return_value=items),
    ):
        response = client.post(
            f"/api/boards/{board.id}/ai/suggestions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"item_count": 2},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    # useBoardAISuggestions reads response.data.items || [] and nothing else.
    assert set(body) == {"items"}
    assert isinstance(body["items"], list) and len(body["items"]) == 2
    allowed_item_keys = {"label", "symbol_key", "color", "linked_board_id", "description"}
    for item in body["items"]:
        assert set(item) <= allowed_item_keys, f"unexpected keys: {set(item) - allowed_item_keys}"
        assert item.get("label"), "every suggestion carries a label"


def test_learning_session_start_contract_matches_ts_response(
    test_db_session, admin_user, admin_token, client: TestClient
):
    """POST /learning/start returns exactly the LearningSessionResponse keys.

    The TS interface declares success/session_id/plan_id/task_id/board_id/
    welcome_message/topic/difficulty/error, and the learningStore additionally
    reads ``provider_used`` off the session response for the provider badge.
    """
    from unittest.mock import MagicMock

    from src.api.deps import get_learning_service

    mock_service = MagicMock()
    mock_service.start_learning_session.return_value = {
        "success": True,
        "session_id": 42,
        "plan_id": None,
        "task_id": None,
        "board_id": None,
        "welcome_message": "Welcome!",
        "topic": "Weather",
        "difficulty": "adaptive",
        "provider_used": "groq",
    }
    app.dependency_overrides[get_learning_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/learning/start",
            params={"user_id": admin_user.id},
            json={"topic": "Weather", "purpose": "practice"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    finally:
        app.dependency_overrides.pop(get_learning_service, None)

    assert response.status_code == 200, response.text
    body = response.json()
    expected_keys = {
        "success",
        "session_id",
        "plan_id",
        "task_id",
        "board_id",
        "welcome_message",
        "topic",
        "difficulty",
        "provider_used",
    }
    assert expected_keys <= set(body), (
        f"missing keys: {expected_keys - set(body)}"
    )
    assert body["success"] is True
    assert body["session_id"] == 42
    assert body["provider_used"] == "groq"
