from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers import board_ai, board_assignments, boards, symbols

client = TestClient(app)


def test_board_domains_are_exposed_as_focused_routers():
    assert boards.router is not None
    assert symbols.router is not None
    assert board_ai.router is not None
    assert board_assignments.router is not None


def test_board_list_accepts_slash_and_no_slash(
    setup_test_db, admin_user, admin_token
):
    headers = {"Authorization": f"Bearer {admin_token}"}

    slash = client.get("/api/boards/", headers=headers)
    no_slash = client.get("/api/boards", headers=headers)

    assert slash.status_code == 200
    assert no_slash.status_code == 200
    assert no_slash.json() == slash.json()
