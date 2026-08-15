import uuid
from contextlib import contextmanager, suppress

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.aac_app.models import BoardAssignment, CommunicationBoard, StudentTeacher, User
from src.aac_app.utils.jwt_utils import create_access_token
from src.api.main import app


@contextmanager
def finish_collab_connections(client, *websockets):
    def drain_connections():
        client.portal.call(app.state.shutdown_event.set)
        for websocket in websockets:
            with suppress(WebSocketDisconnect, RuntimeError):
                websocket.receive()

    try:
        yield
    except BaseException:
        with suppress(Exception):
            drain_connections()
        raise
    else:
        drain_connections()


@pytest.fixture
def collab_client(setup_test_db):
    with TestClient(app) as client:
        try:
            yield client
        finally:
            client.portal.call(app.state.shutdown_event.set)


def test_collab_board_ws_broadcast(test_password, collab_client):
    client = collab_client

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

    # 3. Connect to WebSocket with the bearer token in the negotiated
    # subprotocol rather than exposing it in the URL.
    url = f"/api/collab/boards/{board_id}"

    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws1,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws2,
        finish_collab_connections(client, ws1, ws2),
    ):
        # Send a move operation
        ws1.send_json(
            {"op": "move", "symbol_id": 123, "position": {"x": 1, "y": 2}}
        )

        # Receive on the other connection
        recv = ws2.receive_json()
        assert recv["type"] == "board_change"
        assert recv["payload"]["op"] == "move"
        assert recv["payload"]["symbol_id"] == 123


def test_rostered_teacher_can_join_private_student_board(
    test_db_session, collab_client
):
    student = User(
        username="collab_rostered_student",
        display_name="Collab Rostered Student",
        user_type="student",
        password_hash="test-hash",
    )
    teacher = User(
        username="collab_rostered_teacher",
        display_name="Collab Rostered Teacher",
        user_type="teacher",
        password_hash="test-hash",
    )
    test_db_session.add_all([student, teacher])
    test_db_session.flush()
    test_db_session.add(StudentTeacher(student_id=student.id, teacher_id=teacher.id))
    board = CommunicationBoard(user_id=student.id, name="Rostered Scope Board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    token = create_access_token(
        data={"sub": teacher.username, "user_id": teacher.id, "user_type": teacher.user_type}
    )
    client = collab_client

    with (
        client.websocket_connect(
            f"/api/collab/boards/{board.id}",
            subprotocols=["aac-auth", token],
        ) as websocket,
        finish_collab_connections(client, websocket),
    ):
        pass


def test_assigned_student_can_join_private_board(
    test_db_session, collab_client
):
    student = User(
        username="collab_assigned_student",
        display_name="Collab Assigned Student",
        user_type="student",
        password_hash="test-hash",
    )
    owner = User(
        username="collab_board_owner",
        display_name="Collab Board Owner",
        user_type="teacher",
        password_hash="test-hash",
    )
    test_db_session.add_all([student, owner])
    test_db_session.flush()
    board = CommunicationBoard(user_id=owner.id, name="Assigned Scope Board")
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add(BoardAssignment(board_id=board.id, student_id=student.id))
    test_db_session.commit()
    test_db_session.refresh(board)

    token = create_access_token(
        data={"sub": student.username, "user_id": student.id, "user_type": student.user_type}
    )
    client = collab_client

    with (
        client.websocket_connect(
            f"/api/collab/boards/{board.id}",
            subprotocols=["aac-auth", token],
        ) as websocket,
        finish_collab_connections(client, websocket),
    ):
        pass


def test_inactive_user_cannot_join_collaboration_board(
    test_db_session, collab_client
):
    user = User(
        username="collab_inactive_user",
        display_name="Inactive Collaboration User",
        user_type="teacher",
        password_hash="test-hash",
        is_active=False,
    )
    test_db_session.add(user)
    test_db_session.flush()
    board = CommunicationBoard(user_id=user.id, name="Inactive User Board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "user_type": user.user_type}
    )
    client = collab_client

    with client.websocket_connect(
        f"/api/collab/boards/{board.id}",
        subprotocols=["aac-auth", token],
    ) as websocket, pytest.raises(WebSocketDisconnect) as exc_info:
        websocket.receive_json()

    assert exc_info.value.code == 1008

def test_unrelated_teacher_cannot_join_private_student_board(
    test_db_session, test_password, collab_client
):
    student = User(
        username="collab_scope_student",
        display_name="Collab Scope Student",
        user_type="student",
        password_hash="test-hash",
    )
    teacher = User(
        username="collab_scope_teacher",
        display_name="Collab Scope Teacher",
        user_type="teacher",
        password_hash="test-hash",
    )
    test_db_session.add_all([student, teacher])
    test_db_session.flush()
    board = CommunicationBoard(
        user_id=student.id,
        name="Private Scope Board",
        is_public=False,
    )
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    token = create_access_token(
        data={"sub": teacher.username, "user_id": teacher.id, "user_type": teacher.user_type}
    )
    client = collab_client

    with client.websocket_connect(
        f"/api/collab/boards/{board.id}",
        subprotocols=["aac-auth", token],
    ) as websocket, pytest.raises(WebSocketDisconnect) as exc_info:
        websocket.receive_json()

    assert exc_info.value.code == 1008
