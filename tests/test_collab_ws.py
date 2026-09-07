import uuid
from contextlib import contextmanager, suppress

import pytest
from fastapi import HTTPException
from fastapi import status as fastapi_status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import src.api.routers.collab as collab_module
from src.aac_app.models import BoardAssignment, CommunicationBoard, StudentTeacher, User
from src.aac_app.utils.jwt_utils import create_access_token
from src.api.deps.access import require_board_view_access as real_view
from src.api.main import app
from src.api.routers.collab import ConnectionManager


@contextmanager
def finish_collab_connections(client, *websockets):
    def drain_connections():
        # Ask every live handler to leave its receive loop gracefully (it
        # sends a final 1001 close before returning). Handlers that already
        # returned mid-test (e.g. the sender closed with 1009 for an
        # oversized payload) never send another frame, so a blocking
        # receive() on them would deadlock the teardown. Instead, fully tear
        # each session down: nudge it with a client close, then cancel the
        # session task and reap it. Live handlers exit via their
        # WebSocketDisconnect/CancelledError paths (cleanup still runs);
        # already-exited handlers have their streams closed by the cancel.
        with suppress(Exception):
            client.portal.call(app.state.shutdown_event.set)
        for websocket in websockets:
            with suppress(Exception):
                websocket.close()
            with suppress(Exception):
                websocket.exit_stack.close()

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


def test_connection_manager_removes_empty_rooms():
    manager = ConnectionManager()
    first = object()
    second = object()

    manager.rooms[42] = {first, second}
    manager.disconnect(42, first)
    assert manager.rooms == {42: {second}}

    manager.disconnect(42, second)
    assert manager.rooms == {}


def test_broadcast_removes_failing_socket_and_survives_double_disconnect():
    """A client that never reads (or whose send fails) is dropped from the
    room, later clients still receive the fan-out, and a repeated disconnect
    for the same socket is a harmless no-op (the handler finally-block and
    the broadcast failure path can both run for one socket)."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    manager = ConnectionManager()
    board_id = 7

    zombie = MagicMock()
    zombie.send_json = AsyncMock(side_effect=RuntimeError("backpressure/full"))
    healthy = MagicMock()
    healthy.send_json = AsyncMock()

    manager.rooms[board_id] = {zombie, healthy}

    asyncio.run(manager.broadcast(board_id, {"type": "board_change"}))

    healthy.send_json.assert_awaited_once()
    # The failing socket is gone from the room; the healthy one remains.
    assert zombie not in manager.rooms[board_id]
    assert healthy in manager.rooms[board_id]

    # Double disconnect: the handler's finally block runs after the broadcast
    # already removed the socket; this must not raise or disturb the room.
    manager.disconnect(board_id, zombie)
    assert manager.rooms[board_id] == {healthy}

    # A subsequent broadcast reaches only the healthy socket.
    healthy.send_json.reset_mock()
    asyncio.run(manager.broadcast(board_id, {"type": "board_change"}))
    healthy.send_json.assert_awaited_once()


def test_collab_ws_block_social_messaging(test_db_session, test_password, collab_client):
    """A student whose policy locks social messaging never sees collab
    broadcasts carrying labels; the payload is dropped at the gate."""
    client = collab_client

    from src.aac_app.models import GuardianProfile

    student = User(
        username="collab_locked_student",
        display_name="Collab Locked Student",
        user_type="student",
        password_hash="test-hash",
    )
    test_db_session.add(student)
    test_db_session.flush()
    board = CommunicationBoard(
        user_id=student.id,
        name="Locked Collab Board",
        is_public=False,
    )
    test_db_session.add(board)
    test_db_session.add(
        GuardianProfile(
            user_id=student.id,
            template_name="default",
            safety_constraints={"block_social_messaging": True},
            is_active=True,
            created_by=student.id,
        )
    )
    test_db_session.commit()
    test_db_session.refresh(board)

    token = create_access_token(
        data={"sub": student.username, "user_id": student.id, "user_type": student.user_type}
    )

    url = f"/api/collab/boards/{board.id}"
    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws1,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws2,
        finish_collab_connections(client, ws1, ws2),
    ):
        ws1.send_json({"op": "add", "label": "casa"})
        # A follow-up ping from ws2 must be the FIRST message ws1 receives:
        # if the labeled payload had passed the gate, the add would arrive
        # before the ping.
        ws2.send_json({"op": "ping"})
        recv = ws1.receive_json()
        assert recv["type"] == "board_change"
        assert recv["payload"]["op"] == "ping"

    from src.aac_app.models import ContentSafetyEvent

    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == student.id)
        .first()
    )
    assert event is not None
    assert event.surface == "social" and event.verdict == "blocked"
    assert "block_social_messaging" in (event.detail or "")


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


def test_collab_ws_without_token_rejected(collab_client):
    """A WebSocket connection without an auth subprotocol is refused (1008)."""
    client = collab_client
    with client.websocket_connect("/api/collab/boards/1") as websocket, pytest.raises(
        WebSocketDisconnect
    ) as exc_info:
        websocket.receive_json()

    assert exc_info.value.code == 1008


def test_collab_ws_unknown_board_rejected(test_db_session, test_password, collab_client):
    """A valid token connecting to a nonexistent board is refused (1008)."""
    username = f"ws_ghost_{uuid.uuid4().hex[:8]}"
    reg_response = collab_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": test_password,
            "display_name": "Ghost User",
            "user_type": "teacher",
        },
    )
    assert reg_response.status_code == 200
    login_response = collab_client.post(
        "/api/auth/token", data={"username": username, "password": test_password}
    )
    token = login_response.json()["access_token"]

    with collab_client.websocket_connect(
        "/api/collab/boards/999999",
        subprotocols=["aac-auth", token],
    ) as websocket, pytest.raises(WebSocketDisconnect) as exc_info:
        websocket.receive_json()

    assert exc_info.value.code == 1008


def test_collab_ws_unassigned_student_rejected(test_db_session, collab_client):
    """A student without a board assignment cannot join a private board (1008)."""
    student = User(
        username="collab_unassigned_student",
        display_name="Unassigned Student",
        user_type="student",
        password_hash="test-hash",
    )
    teacher = User(
        username="collab_owner_teacher",
        display_name="Owner Teacher",
        user_type="teacher",
        password_hash="test-hash",
    )
    test_db_session.add_all([student, teacher])
    test_db_session.flush()
    board = CommunicationBoard(user_id=teacher.id, name="Private Teacher Board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    token = create_access_token(
        data={
            "sub": student.username,
            "user_id": student.id,
            "user_type": student.user_type,
        }
    )
    client = collab_client
    with client.websocket_connect(
        f"/api/collab/boards/{board.id}",
        subprotocols=["aac-auth", token],
    ) as websocket, pytest.raises(WebSocketDisconnect) as exc_info:
        websocket.receive_json()

    assert exc_info.value.code == 1008


def test_collab_ws_broadcast_skips_sender(
    test_password, collab_client
):
    """A broadcast is delivered to the other client but not echoed to the sender."""
    client = collab_client
    username = f"ws_duo_{uuid.uuid4().hex[:8]}"
    reg_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": test_password,
            "display_name": "Duo User",
            "user_type": "teacher",
        },
    )
    user_id = reg_response.json()["id"]
    login_response = client.post(
        "/api/auth/token", data={"username": username, "password": test_password}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    board_response = client.post(
        "/api/boards",
        headers=headers,
        params={"user_id": user_id},
        json={"name": "Duo Board", "grid_rows": 3, "grid_cols": 4},
    )
    board_id = board_response.json()["id"]
    url = f"/api/collab/boards/{board_id}"

    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws1,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws2,
        finish_collab_connections(client, ws1, ws2),
    ):
        ws1.send_json({"op": "move", "symbol_id": 1})
        recv = ws2.receive_json()
        assert recv["payload"]["symbol_id"] == 1

        # ws2 responds; ws1 receives it and ws2's own socket stays usable
        # (the sender is skipped in the broadcast).
        ws2.send_json({"op": "move", "symbol_id": 2})
        recv = ws1.receive_json()
        assert recv["payload"]["symbol_id"] == 2
        ws2.send_json({"op": "ping"})


def test_collab_ws_oversized_payload_closes_sender_with_1009(
    test_db_session, test_password, collab_client
):
    """A payload over the 256KB collaboration cap closes the sender (1009).

    The oversized message must never be fanned out: the receiving peer's first
    message is the next NORMAL broadcast, proving the giant payload never
    arrived ahead of it.
    """
    client = collab_client
    username = f"ws_oversize_{uuid.uuid4().hex[:8]}"
    reg_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": test_password,
            "display_name": "Oversize User",
            "user_type": "teacher",
        },
    )
    user_id = reg_response.json()["id"]
    login_response = client.post(
        "/api/auth/token", data={"username": username, "password": test_password}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    board_response = client.post(
        "/api/boards",
        headers=headers,
        params={"user_id": user_id},
        json={"name": "Oversize Board", "grid_rows": 3, "grid_cols": 4},
    )
    board_id = board_response.json()["id"]
    url = f"/api/collab/boards/{board_id}"

    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as sender,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as observer,
        finish_collab_connections(client, sender, observer),
    ):
        # ~400KB of JSON payload is well over the 256KB cap but comfortably
        # under the ASGI server's default receive limit.
        sender.send_json({"op": "add", "blob": "x" * 400_000})
        # The observer's own next normal message must be what the peer
        # receives first: had the giant payload fanned out, it would be first.
        observer.send_json({"op": "ping"})
        # In the unfixed code the sender stays connected and receives the
        # observer's ping; after the fix the sender was closed with 1009.
        with pytest.raises(WebSocketDisconnect) as exc_info:
            sender.receive_json()
        assert exc_info.value.code == 1009


def test_collab_ws_oversized_payload_is_not_fanned_out(
    test_db_session, test_password, collab_client
):
    """A giant payload is dropped at the sender, so peers only ever see
    normal-size broadcasts."""
    client = collab_client
    username = f"ws_no_fanout_{uuid.uuid4().hex[:8]}"
    reg_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": test_password,
            "display_name": "No Fanout User",
            "user_type": "teacher",
        },
    )
    user_id = reg_response.json()["id"]
    login_response = client.post(
        "/api/auth/token", data={"username": username, "password": test_password}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    board_response = client.post(
        "/api/boards",
        headers=headers,
        params={"user_id": user_id},
        json={"name": "No Fanout Board", "grid_rows": 3, "grid_cols": 4},
    )
    board_id = board_response.json()["id"]
    url = f"/api/collab/boards/{board_id}"

    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as sender,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as peer_a,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as peer_b,
        finish_collab_connections(client, sender, peer_a, peer_b),
    ):
        sender.send_json({"op": "add", "blob": "y" * 400_000})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            sender.receive_json()
        assert exc_info.value.code == 1009

        # peer_a broadcasts a small message; peer_b must see THAT first.
        peer_a.send_json({"op": "move", "symbol_id": 42})
        first = peer_b.receive_json()
        assert first["type"] == "board_change"
        assert first["payload"]["symbol_id"] == 42


def test_collab_ws_public_viewer_cannot_broadcast(
    test_db_session, test_password, collab_client
):
    """A public-board viewer (no owner/admin/roster/assignment) receives
    broadcasts but its own messages are never re-emitted to the room."""
    viewer = User(
        username="collab_viewer_mute",
        display_name="Muted Public Viewer",
        user_type="student",
        password_hash="test-hash",
    )
    test_db_session.add(viewer)
    test_db_session.commit()

    username = f"ws_public_mute_{uuid.uuid4().hex[:8]}"
    reg_response = collab_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": test_password,
            "display_name": "Public Mute Owner",
            "user_type": "teacher",
        },
    )
    user_id = reg_response.json()["id"]
    login_response = collab_client.post(
        "/api/auth/token", data={"username": username, "password": test_password}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    board_response = collab_client.post(
        "/api/boards",
        headers=headers,
        params={"user_id": user_id},
        json={
            "name": "Public Mute Board",
            "grid_rows": 3,
            "grid_cols": 4,
            "is_public": True,
        },
    )
    board_id = board_response.json()["id"]

    viewer_token = create_access_token(
        data={
            "sub": viewer.username,
            "user_id": viewer.id,
            "user_type": viewer.user_type,
        }
    )
    url = f"/api/collab/boards/{board_id}"
    with (
        collab_client.websocket_connect(url, subprotocols=["aac-auth", token]) as owner_a,
        collab_client.websocket_connect(url, subprotocols=["aac-auth", token]) as owner_b,
        collab_client.websocket_connect(
            url, subprotocols=["aac-auth", viewer_token]
        ) as viewer_ws,
        finish_collab_connections(collab_client, owner_a, owner_b, viewer_ws),
    ):
        # The viewer's attempt to edit must be swallowed silently (read-only):
        # had it fanned out, owner_a would receive it BEFORE the ping that
        # owner_b broadcasts next.
        viewer_ws.send_json({"op": "move", "symbol_id": 99})
        owner_b.send_json({"op": "ping"})
        recv = owner_a.receive_json()
        assert recv["type"] == "board_change"
        assert recv["payload"]["op"] == "ping"


def test_collab_ws_public_board_read_only_viewer(
    test_db_session, test_password, collab_client
):
    """A user without access can join a public board and receive broadcasts."""
    viewer = User(
        username="collab_public_viewer",
        display_name="Public Viewer",
        user_type="student",
        password_hash="test-hash",
    )
    test_db_session.add(viewer)
    test_db_session.commit()

    username = f"ws_public_{uuid.uuid4().hex[:8]}"
    reg_response = collab_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": test_password,
            "display_name": "Public Owner",
            "user_type": "teacher",
        },
    )
    user_id = reg_response.json()["id"]
    login_response = collab_client.post(
        "/api/auth/token", data={"username": username, "password": test_password}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    board_response = collab_client.post(
        "/api/boards",
        headers=headers,
        params={"user_id": user_id},
        json={"name": "Public Board", "grid_rows": 3, "grid_cols": 4, "is_public": True},
    )
    board_id = board_response.json()["id"]

    viewer_token = create_access_token(
        data={
            "sub": viewer.username,
            "user_id": viewer.id,
            "user_type": viewer.user_type,
        }
    )
    url = f"/api/collab/boards/{board_id}"
    with (
        collab_client.websocket_connect(url, subprotocols=["aac-auth", token]) as owner_ws,
        collab_client.websocket_connect(
            url, subprotocols=["aac-auth", viewer_token]
        ) as viewer_ws,
        finish_collab_connections(collab_client, owner_ws, viewer_ws),
    ):
        owner_ws.send_json({"op": "move", "symbol_id": 7})
        recv = viewer_ws.receive_json()
        assert recv["payload"]["symbol_id"] == 7


def _make_collab_room(client, test_password, tag):
    """Register a teacher, create a board and return (token, ws url)."""
    username = f"{tag}_{uuid.uuid4().hex[:8]}"
    reg_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": test_password,
            "display_name": "Collab Room",
            "user_type": "teacher",
        },
    )
    user_id = reg_response.json()["id"]
    login_response = client.post(
        "/api/auth/token", data={"username": username, "password": test_password}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    board_response = client.post(
        "/api/boards",
        headers=headers,
        params={"user_id": user_id},
        json={"name": "Collab Room", "grid_rows": 3, "grid_cols": 4},
    )
    board_id = board_response.json()["id"]
    return token, f"/api/collab/boards/{board_id}"


def test_collab_ws_multibyte_payload_over_cap_closes_with_1009(
    test_db_session, test_password, collab_client
):
    """The 256KB cap counts WIRE bytes, not str code points: a non-ASCII
    payload of 200K chars is ~400KB encoded (2 bytes/char) and must be
    refused with 1009 even though its char count is under 256K."""
    client = collab_client
    token, url = _make_collab_room(client, test_password, "ws_mb_over")
    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as sender,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as observer,
        finish_collab_connections(client, sender, observer),
    ):
        # 200_000 chars x 2 bytes = ~400KB on the wire: over 256KB even
        # though len(str) == 200_000 is under 262_144 code points.
        blob = "\u00e9" * 200_000  # "é"
        assert len(blob) < 262_144  # would pass a char-count cap
        sender.send_json({"op": "add", "blob": blob})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            sender.receive_json()
        assert exc_info.value.code == 1009
        # The observer must never receive the giant multibyte payload.
        observer.send_json({"op": "ping"})


def test_collab_ws_multibyte_payload_under_cap_is_fanned_out_intact(
    test_db_session, test_password, collab_client
):
    """A multibyte payload under the byte cap reaches peers byte-for-byte."""
    client = collab_client
    token, url = _make_collab_room(client, test_password, "ws_mb_ok")
    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as sender,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as observer,
        finish_collab_connections(client, sender, observer),
    ):
        # 50_000 chars x 2 bytes = 100KB on the wire: comfortably under the
        # cap and must broadcast normally.
        blob = "\u00e9" * 50_000
        sender.send_json({"op": "add", "blob": blob})
        recv = observer.receive_json()
        assert recv["type"] == "board_change"
        assert recv["payload"]["blob"] == blob


def test_collab_ws_non_403_access_error_propagates_as_1011(
    test_db_session, test_password, collab_client, monkeypatch
):
    """An HTTPException that is not the intentional 403 (e.g. a 500 from the
    access helper) must terminate the socket with a server error, never
    silently degrade to "denied" (1008) or read-only."""

    def _boom(board, user, db):
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="boom",
        )

    client = collab_client
    token, url = _make_collab_room(client, test_password, "ws_except")

    monkeypatch.setattr(collab_module, "require_board_view_access", _boom)
    # The session handshake (and therefore the 1011 close) happens on
    # ``__enter__``, so the connect must be used as a context manager here.
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(url, subprotocols=["aac-auth", token]),
    ):
        pass
    assert exc_info.value.code == 1011

    # Same for the broadcast gate: the real view gate passes (the socket is
    # the board owner), but a 500 from the write helper must propagate
    # instead of silently demoting the owner to read-only.
    monkeypatch.setattr(collab_module, "require_board_view_access", real_view)
    monkeypatch.setattr(collab_module, "require_board_collab_write_access", _boom)
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(url, subprotocols=["aac-auth", token]),
    ):
        pass
    assert exc_info.value.code == 1011


def test_collab_ws_content_gate_error_drops_message_fail_closed(
    test_db_session, test_password, collab_client, monkeypatch
):
    """When the content-safety gate itself raises, the labeled message must be
    DROPPED (fail closed): a label that could not be vetted must never be
    fanned out to the room, and the connection stays usable."""
    client = collab_client
    token, url = _make_collab_room(client, test_password, "ws_gate_err")

    import src.aac_app.services.content_safety as content_safety

    def _explode(text, *args, **kwargs):
        raise RuntimeError("gate down")

    monkeypatch.setattr(content_safety, "check_text", _explode)

    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws_a,
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as ws_b,
        finish_collab_connections(client, ws_a, ws_b),
    ):
        # A labeled message whose gate check raises must be dropped.
        ws_a.send_json({"op": "add", "label": "casa"})
        # The peer's first message must be the NEXT normal broadcast (the
        # dropped label must never precede it).
        ws_a.send_json({"op": "ping"})
        first = ws_b.receive_json()
        assert first["payload"]["op"] == "ping"
        # Both sockets remain usable.
        ws_b.send_json({"op": "ping"})
        second = ws_a.receive_json()
        assert second["payload"]["op"] == "ping"


def test_collab_ws_broadcast_error_closes_sender_with_1011(
    test_db_session, test_password, collab_client, monkeypatch
):
    """An unexpected error in the inner loop (e.g. a broadcast failure) closes
    the socket with an explicit 1011 instead of leaving it half-open."""
    from unittest.mock import AsyncMock

    client = collab_client
    token, url = _make_collab_room(client, test_password, "ws_bcast_err")

    monkeypatch.setattr(
        collab_module.manager,
        "broadcast",
        AsyncMock(side_effect=RuntimeError("broadcast exploded")),
    )
    with (
        client.websocket_connect(url, subprotocols=["aac-auth", token]) as sender,
        finish_collab_connections(client, sender),
    ):
        sender.send_json({"op": "move", "symbol_id": 1})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            sender.receive_json()
        assert exc_info.value.code == 1011
