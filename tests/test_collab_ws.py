import uuid

from fastapi.testclient import TestClient

from src.api.main import app


def test_collab_board_ws_broadcast(test_password):
    client = TestClient(app)

    # 1. Create a user
    username = f"ws_user_{uuid.uuid4().hex[:8]}"
    password = test_password
    reg_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "display_name": "WS User",
            "user_type": "teacher",
        },
    )
    assert reg_response.status_code == 200
    user_data = reg_response.json()
    user_id = user_data["id"]

    # Login to get real token
    login_response = client.post(
        "/api/auth/token", data={"username": username, "password": password}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create a board for this user
    board_response = client.post(
        "/api/boards",
        headers=headers,
        params={"user_id": user_id},
        json={"name": "WS Test Board", "grid_rows": 3, "grid_cols": 4},
    )
    assert board_response.status_code == 200
    board_id = board_response.json()["id"]

    # 3. Connect to WebSocket with token
    # Note: TestClient.websocket_connect takes a URL. We append the token query param.
    url = f"/api/collab/boards/{board_id}?token={token}"

    with client.websocket_connect(url) as ws1:
        with client.websocket_connect(url) as ws2:
            # Send a move operation
            ws1.send_json(
                {"op": "move", "symbol_id": 123, "position": {"x": 1, "y": 2}}
            )

            # Receive on the other connection
            recv = ws2.receive_json()
            assert recv["type"] == "board_change"
            assert recv["payload"]["op"] == "move"
            assert recv["payload"]["symbol_id"] == 123
