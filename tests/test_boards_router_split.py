from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import CommunicationBoard
from src.api.main import app
from src.api.routers import board_ai, board_assignments, boards, symbols


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_board_domains_are_exposed_as_focused_routers():
    assert boards.router is not None
    assert symbols.router is not None
    assert board_ai.router is not None
    assert board_assignments.router is not None


def test_board_list_returns_server_error_when_query_fails(
    setup_test_db, admin_user, admin_token, client
):
    broken_db = Mock()
    broken_db.query.side_effect = RuntimeError("database unavailable")
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    from src.api.deps import get_current_active_user, get_db

    def override_get_db():
        yield broken_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    try:
        response = client.get(
            "/api/boards/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

    assert response.status_code == 500
    assert response.json()["detail"]


def test_board_list_returns_server_error_when_serialization_fails(
    setup_test_db, test_db_session, admin_user, admin_token, monkeypatch, client
):
    test_db_session.add(
        CommunicationBoard(
            user_id=admin_user.id,
            name="Serialization failure board",
        )
    )
    test_db_session.commit()
    serialize_mock = Mock(side_effect=RuntimeError("serialization failed"))
    monkeypatch.setattr(boards, "serialize_board", serialize_mock)
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    from src.api.deps import get_current_active_user, get_db

    def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    try:
        response = client.get(
            "/api/boards/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

    assert response.status_code == 500
    assert response.json()["detail"]
    serialize_mock.assert_called_once()


def test_board_list_accepts_slash_and_no_slash(
    setup_test_db, admin_user, admin_token, client
):
    headers = {"Authorization": f"Bearer {admin_token}"}

    slash = client.get("/api/boards/", headers=headers)
    no_slash = client.get("/api/boards", headers=headers)

    assert slash.status_code == 200
    assert no_slash.status_code == 200
    assert no_slash.json() == slash.json()
