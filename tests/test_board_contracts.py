"""Contract tests pinning backend response shapes consumed by the frontend.

These exist so the backend↔frontend contracts audited by hand are enforced
mechanically instead of "verified by eye":
- serialize_board never emits ``symbol: null`` for a persisted placement
  (the TS ``BoardSymbol.symbol`` type is non-nullable);
- the ``/users/assign-student`` idempotency payload is exactly
  ``{message, status}`` with ``status in {"created", "exists"}``;
- the LM Studio model-listing divergence (compat route returns 200 with an
  ``error`` key, canonical route raises 503) is intentional and pinned.
"""

import pytest
from fastapi.testclient import TestClient

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
