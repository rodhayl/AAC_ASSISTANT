import uuid

from fastapi.testclient import TestClient

from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)


def test_board_grid_fields_present_and_updatable(test_password):
    # Register a user
    username = f"grid_user_{uuid.uuid4().hex[:8]}"
    password = test_password
    reg_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "display_name": "Grid User",
            "user_type": "teacher",
        },
    )
    assert reg_response.status_code == 200
    user_id = reg_response.json()["id"]
    headers = create_test_headers(user_id, username, "teacher")

    # Create board
    payload = {
        "name": "Test Board",
        "description": "Grid test",
        "category": "general",
        "is_public": False,
        "is_template": False,
        "grid_rows": 3,
        "grid_cols": 3,
    }
    # Removed params={"user_id": 1} and added headers
    res = client.post(
        "/api/boards/", json=payload, headers=headers, params={"user_id": user_id}
    )
    assert res.status_code == 200, res.text
    board = res.json()
    assert board["grid_rows"] == 3
    assert board["grid_cols"] == 3

    # Update grid
    update = payload.copy()
    update["grid_rows"] = 4
    update["grid_cols"] = 4
    res2 = client.put(f"/api/boards/{board['id']}", json=update, headers=headers)
    assert res2.status_code == 200
    updated = res2.json()
    assert updated["grid_rows"] == 4
    assert updated["grid_cols"] == 4
