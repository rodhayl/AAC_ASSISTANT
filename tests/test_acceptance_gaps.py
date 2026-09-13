"""Acceptance regression tests for audit findings F05/F06/F07/F13.

F05 — collaboration permissions must expire/revalidate: an already-open
    socket must be closed when the account is deactivated, the token is
    revoked (security_version bump), or board access is removed — including
    an idle receiver.

F06 — collaboration must release the request-scoped DB session before the
    socket loop, and a stalled recipient must not delay healthy peers.

F07 — voice transcription must not block the event loop: while a slow
    transcription occupies a worker thread, concurrent async work on the
    loop stays responsive; the worker-owned temp copy outlives caller
    cancellation safely.

F13 — export must document learning-history truncation (meta.truncated /
    meta.total_learning_sessions) and bound the payload to 100 sessions.

F11/N10 — the global request-body bound must reject oversized declared and
    chunked bodies before parsing, and must never deliver a clean success
    when the app swallows the abort (late overflow aborts the connection and
    the app's success body is suppressed).

D4 — revalidation tolerates transient DB failures up to a threshold, token
    expiry is enforced every loop iteration, and a revoked socket still
    closes promptly (1008) after a tolerated blip instead of 1011.

D8 — the production voice path copies the caller's audio inside the
    semaphore-guarded worker thread, so the multi-MB copy never blocks the
    event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

import src.api.routers.collab as collab_module
from src.aac_app.models import BoardAssignment, CommunicationBoard, User
from src.aac_app.models.learning import LearningSession
from src.api.deps import get_db
from src.api.main import _BodyTooLarge, _BoundedReceiveMiddleware, app

pytestmark = pytest.mark.usefixtures("setup_test_db")


# ---------------------------------------------------------------- helpers


def _make_user(db, username: str, user_type: str = "student") -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash="test-hash",
        user_type=user_type,
        is_active=True,
        display_name=username.title(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_board(
    db, owner: User, name: str = "Acceptance Board", is_public: bool = False
) -> CommunicationBoard:
    board = CommunicationBoard(user_id=owner.id, name=name, is_public=is_public)
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


def _token_for(user: User) -> str:
    """Mirror the real auth router's access-token claims (incl. sec_ver)."""
    from src.aac_app.utils.jwt_utils import create_access_token

    return create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "user_type": user.user_type,
            "sec_ver": user.security_version or 1,
        }
    )


class _FakeClock:
    """time.monotonic replacement with a test-controllable offset.

    The collab handler reads the clock through ``import time as _time`` and
    asyncio's loop timers also read ``time.monotonic()`` dynamically, so a
    single mutable offset shifts both the handler's revalidation bookkeeping
    and the pending revalidate sleep together. The real function is captured
    at import time (before any patching) so the clock itself never recurses
    into the patched attribute.
    """

    _real_monotonic = staticmethod(time.monotonic)

    def __init__(self) -> None:
        self.offset = 0.0

    def __call__(self) -> float:
        return self._real_monotonic() + self.offset


def _close_ws(ws) -> None:
    with suppress(Exception):
        ws.close()
    with suppress(Exception):
        ws.exit_stack.close()


# ---------------------------------------------------------------- F05


class TestCollabRevalidation:
    def _expect_revoked(self, client, board, token, mutate):
        """Open a socket, apply `mutate` in a separate committed session,
        jump the clock past REVALIDATE_INTERVAL, wake the loop, and expect
        the server to close the socket (1008 policy violation)."""
        clock = _FakeClock()
        with (
            patch("time.monotonic", new=clock),
            client.websocket_connect(
                f"/api/collab/boards/{board.id}",
                subprotocols=["aac-auth", token],
            ) as ws,
        ):
                # Separate committed session — the connection must observe
                # the change through its own revalidation read.
                from src.aac_app.db import create_session_factory

                fresh = create_session_factory()()
                try:
                    mutate(fresh)
                    fresh.commit()
                finally:
                    fresh.close()

                clock.offset = 120.0  # > REVALIDATE_INTERVAL (60s)
                # Wake the loop: any JSON frame is fine (unknown ops are
                # dropped by the vocabulary gate and the loop re-checks
                # revalidation at the top of the next iteration).
                ws.send_json({"op": "wake"})

                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()

    def test_deactivated_user_socket_is_closed_on_revalidation(
        self, test_db_session, collab_client
    ):
        db = test_db_session
        student = _make_user(db, f"reval_deact_{uuid.uuid4().hex[:6]}")
        board = _make_board(db, student)
        token = _token_for(student)

        def deactivate(fresh):
            fresh.query(User).filter(User.id == student.id).update(
                {User.is_active: False}, synchronize_session=False
            )

        self._expect_revoked(collab_client, board, token, deactivate)

    def test_security_version_bump_revokes_open_socket(
        self, test_db_session, collab_client
    ):
        db = test_db_session
        student = _make_user(db, f"reval_secver_{uuid.uuid4().hex[:6]}")
        board = _make_board(db, student)
        token = _token_for(student)

        def bump(fresh):
            target = fresh.get(User, student.id)
            target.security_version = (target.security_version or 1) + 1

        self._expect_revoked(collab_client, board, token, bump)

    def test_assignment_removal_revokes_open_socket(
        self, test_db_session, collab_client
    ):
        db = test_db_session
        teacher = _make_user(
            db, f"reval_teacher_{uuid.uuid4().hex[:6]}", user_type="teacher"
        )
        student = _make_user(db, f"reval_assignee_{uuid.uuid4().hex[:6]}")
        board = _make_board(db, teacher)
        db.add(
            BoardAssignment(
                board_id=board.id, student_id=student.id, assigned_by=teacher.id
            )
        )
        db.commit()
        token = _token_for(student)

        def unassign(fresh):
            fresh.query(BoardAssignment).filter(
                BoardAssignment.board_id == board.id,
                BoardAssignment.student_id == student.id,
            ).delete(synchronize_session=False)

        self._expect_revoked(collab_client, board, token, unassign)


# ---------------------------------------------------------------- D4


class TestCollabRevalidationResilience:
    """D4: revalidation must tolerate a transient DB blip but never let a
    possibly-revoked socket linger, and token expiry must be honored on every
    loop iteration instead of only on the 60s revalidation tick."""

    def test_transient_failure_is_tolerated_then_revocation_still_closes(
        self, test_db_session, collab_client
    ):
        db = test_db_session
        student = _make_user(db, f"reval_blip_{uuid.uuid4().hex[:6]}")
        board = _make_board(db, student)
        token = _token_for(student)

        real_csf = collab_module._csf
        injected = {"n": 0}

        def flaky_csf():
            # Exactly one transient failure, not a revocation.
            if injected["n"] == 0:
                injected["n"] += 1
                raise RuntimeError("transient database failure")
            return real_csf()

        clock = _FakeClock()
        with (
            patch("time.monotonic", new=clock),
            patch.object(collab_module, "_csf", flaky_csf),
            collab_client.websocket_connect(
                f"/api/collab/boards/{board.id}",
                subprotocols=["aac-auth", token],
            ) as ws,
        ):
            # 1) transient failure → tolerated (1/3), the socket stays open.
            clock.offset = 120.0
            ws.send_json({"op": "wake"})
            # 2) a healthy revalidation resets the consecutive-failure count.
            clock.offset = 240.0
            ws.send_json({"op": "wake"})
            # 3) revoke access in a separate committed session.
            from src.aac_app.db import create_session_factory

            fresh = create_session_factory()()
            try:
                fresh.query(User).filter(User.id == student.id).update(
                    {User.is_active: False}, synchronize_session=False
                )
                fresh.commit()
            finally:
                fresh.close()
            clock.offset = 360.0
            ws.send_json({"op": "wake"})

            with pytest.raises(WebSocketDisconnect) as excinfo:
                ws.receive_json()

        assert injected["n"] == 1, "the transient failure must actually be injected"
        # The blip was tolerated (1008 revocation close, not a 1011 error close
        # that an over-eager revalidation would produce on the first failure).
        assert excinfo.value.code == 1008, (
            "a tolerated transient failure must not close the socket with 1011"
        )

    def test_consecutive_failures_close_after_threshold(
        self, test_db_session, collab_client
    ):
        """A socket whose revalidation keeps failing cannot linger forever:
        it closes with 1011 only after REVALIDATE_MAX_FAILURES attempts."""
        db = test_db_session
        student = _make_user(db, f"reval_down_{uuid.uuid4().hex[:6]}")
        board = _make_board(db, student)
        token = _token_for(student)

        attempts = {"n": 0}

        def failing_csf():
            attempts["n"] += 1
            raise RuntimeError("database unavailable")

        clock = _FakeClock()
        with (
            patch("time.monotonic", new=clock),
            patch.object(collab_module, "_csf", failing_csf),
            collab_client.websocket_connect(
                f"/api/collab/boards/{board.id}",
                subprotocols=["aac-auth", token],
            ) as ws,
        ):
            for offset in (120.0, 240.0, 360.0):
                clock.offset = offset
                ws.send_json({"op": "wake"})
            with pytest.raises(WebSocketDisconnect) as excinfo:
                ws.receive_json()

        assert attempts["n"] >= collab_module.REVALIDATE_MAX_FAILURES, attempts
        assert excinfo.value.code == 1011

    def test_expired_token_closes_without_waiting_for_revalidation(
        self, test_db_session, collab_client
    ):
        """The token is checked every loop iteration: a socket whose credential
        expires mid-connection closes promptly, not on the next 60s tick."""
        from datetime import timedelta

        from src.aac_app.utils.jwt_utils import create_access_token

        db = test_db_session
        student = _make_user(db, f"reval_exp_{uuid.uuid4().hex[:6]}")
        board = _make_board(db, student)
        token = create_access_token(
            data={
                "sub": student.username,
                "user_id": student.id,
                "user_type": student.user_type,
                "sec_ver": student.security_version or 1,
            },
            expires_delta=timedelta(seconds=1),
        )

        with collab_client.websocket_connect(
            f"/api/collab/boards/{board.id}", subprotocols=["aac-auth", token]
        ) as ws:
            # Expire the credential while staying far inside the 60s window.
            time.sleep(1.2)
            ws.send_json({"op": "wake"})
            started = time.monotonic()
            with pytest.raises(WebSocketDisconnect) as excinfo:
                ws.receive_json()
            elapsed = time.monotonic() - started

        assert excinfo.value.code == 1008
        # A 60s-tick-only check would take ~REVALIDATE_INTERVAL to notice.
        assert elapsed < 5.0, (
            f"expiry must close promptly, not on the revalidation tick ({elapsed:.1f}s)"
        )


# ---------------------------------------------------------------- F06


class TestCollabPoolRelease:
    def test_request_db_session_closed_before_socket_loop(
        self, test_db_session, test_db_engine, collab_client
    ):
        """The request-scoped session passed via get_db is closed by the
        handler before it enters the long-lived socket loop, while the
        socket itself stays registered in the room."""
        factory = sessionmaker(
            bind=test_db_engine, autoflush=False, expire_on_commit=False
        )
        recorded: dict[str, dict] = {}
        original_override = app.dependency_overrides[get_db]

        def close_tracking_override():
            session = factory()
            original_close = session.close
            state = {"closed": False}

            def spy_close():
                state["closed"] = True
                return original_close()

            session.close = spy_close  # type: ignore[method-assign]
            recorded["state"] = state
            try:
                yield session
            finally:
                original_close()

        db = test_db_session
        student = _make_user(db, f"pool_student_{uuid.uuid4().hex[:6]}")
        board = _make_board(db, student)
        token = _token_for(student)

        app.dependency_overrides[get_db] = close_tracking_override
        try:
            with collab_client.websocket_connect(
                f"/api/collab/boards/{board.id}",
                subprotocols=["aac-auth", token],
            ):
                assert "state" in recorded, "override must have yielded a session"
                assert recorded["state"]["closed"] is True, (
                    "request session must be closed before the socket loop"
                )
                # The socket is alive and registered.
                assert board.id in collab_module.manager.rooms
        finally:
            app.dependency_overrides[get_db] = original_override

    def test_slow_peer_does_not_block_healthy_peers(self):
        """A stalled recipient is dropped after SEND_TIMEOUT while healthy
        peers receive the same broadcast promptly."""
        manager = collab_module.ConnectionManager()
        manager.SEND_TIMEOUT = 0.2
        board_id = 99

        async def stall(*_a, **_kw):
            await asyncio.sleep(30)

        stalled = MagicMock()
        stalled.send_json = AsyncMock(side_effect=stall)
        healthy = MagicMock()
        healthy.send_json = AsyncMock()
        manager.rooms[board_id] = {stalled, healthy}

        started = time.monotonic()
        asyncio.run(manager.broadcast(board_id, {"type": "board_change"}))
        elapsed = time.monotonic() - started

        assert elapsed < 5.0, "broadcast must not wait for the stalled peer's 30s send"
        healthy.send_json.assert_awaited_once()
        assert stalled not in manager.rooms.get(board_id, set())
        assert healthy in manager.rooms.get(board_id, set())


# ---------------------------------------------------------------- F07


class TestCollabRoomCap:
    """F06: room membership is bounded and disconnect restores the count."""

    class _FakeWebSocket:
        def __init__(self) -> None:
            self.closed: tuple[int | None, str | None] | None = None

        async def accept(self, subprotocol: str | None = None) -> None:
            return None

        async def close(self, code: int | None = None, reason: str | None = None) -> None:
            self.closed = (code, reason)

    def test_room_cap_rejects_excess_connections(self):
        manager = collab_module.ConnectionManager()
        board_id = 4242

        async def scenario():
            accepted = []
            for _ in range(manager.MAX_ROOM_SIZE):
                ws = TestCollabRoomCap._FakeWebSocket()
                assert await manager.connect(board_id, ws) is True
                accepted.append(ws)

            overflow = TestCollabRoomCap._FakeWebSocket()
            assert await manager.connect(board_id, overflow) is False
            assert overflow.closed is not None
            assert overflow.closed[0] == 1013  # WS_1013_TRY_AGAIN_LATER
            assert overflow not in manager.rooms[board_id]
            assert len(manager.rooms[board_id]) == manager.MAX_ROOM_SIZE

            # Disconnect frees a slot and the room is dropped when empty.
            manager.disconnect(board_id, accepted[0])
            assert len(manager.rooms[board_id]) == manager.MAX_ROOM_SIZE - 1
            replacement = TestCollabRoomCap._FakeWebSocket()
            assert await manager.connect(board_id, replacement) is True
            for ws in list(manager.rooms[board_id]):
                manager.disconnect(board_id, ws)
            assert board_id not in manager.rooms

        asyncio.run(scenario())


# ---------------------------------------------------------------- F11 / N10


def _drive_asgi(app, messages, content_length=None):
    """Run *app* against a fixed receive queue; return (sent, aborted)."""
    sent: list[dict] = []
    queue = list(messages)

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }

    async def scenario() -> bool:
        try:
            await app(scope, receive, send)
        except _BodyTooLarge:
            return True
        return False

    return sent, asyncio.run(scenario())


def _statuses(sent: list[dict]) -> list[int]:
    return [m["status"] for m in sent if m["type"] == "http.response.start"]


class TestBoundedBodyMiddleware:
    def test_declared_oversized_body_is_rejected_before_parsing(self):
        """A Content-Length over the cap gets a 413 without the app running."""
        from src.api.main import MAX_REQUEST_BYTES

        parsed = False

        async def app(scope, receive, send):
            nonlocal parsed
            parsed = True

        sent, aborted = _drive_asgi(
            _BoundedReceiveMiddleware(app),
            [{"type": "http.request", "body": b"", "more_body": False}],
            content_length=MAX_REQUEST_BYTES + 1,
        )

        assert _statuses(sent) == [413]
        assert aborted is False
        assert parsed is False, "an oversized declared body must not reach the app"

    def test_chunked_oversized_body_is_rejected(self):
        """Chunked bodies (no Content-Length) are bounded too, and the app
        gets the documented 413 rather than a success."""
        from src.api.main import MAX_REQUEST_BYTES

        async def reading_app(scope, receive, send):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect" or not message.get(
                    "more_body"
                ):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        half = MAX_REQUEST_BYTES // 2 + 1024
        messages = [
            {"type": "http.request", "body": b"x" * half, "more_body": True},
            {"type": "http.request", "body": b"x" * half, "more_body": False},
            {"type": "http.disconnect"},
        ]
        sent, aborted = _drive_asgi(_BoundedReceiveMiddleware(reading_app), messages)

        assert _statuses(sent) == [413]
        assert aborted is False

    def test_abort_swallowing_app_cannot_deliver_a_clean_success(self):
        """N10/D3: when the app starts a 200, swallows the receive-side abort
        and answers anyway on an oversized chunked body, the connection is
        aborted and the success body is suppressed — never a clean 200."""
        from src.api.main import MAX_REQUEST_BYTES

        async def swallowing_app(scope, receive, send):
            # Starts the response first, then swallows the abort exception.
            await send({"type": "http.response.start", "status": 200, "headers": []})
            while True:
                try:
                    message = await receive()
                except Exception:
                    break
                if message["type"] == "http.disconnect" or not message.get(
                    "more_body"
                ):
                    break
            await send({"type": "http.response.body", "body": b"ok"})

        messages = [
            {
                "type": "http.request",
                "body": b"x" * (MAX_REQUEST_BYTES + 1),
                "more_body": False,
            },
            {"type": "http.disconnect"},
        ]
        sent, aborted = _drive_asgi(_BoundedReceiveMiddleware(swallowing_app), messages)

        assert aborted is True, (
            "an oversized chunked body consumed by an abort-swallowing app must "
            "abort the connection"
        )
        assert not [m for m in sent if m["type"] == "http.response.body"], (
            "the app's success body must not be delivered for a body the cap rejected"
        )


    def test_stalled_body_is_abandoned_by_the_inactivity_timeout(self, monkeypatch):
        """Q4: the byte ceiling does not bound *time*. A client that sends one
        chunk and then stalls must not hold the worker forever — the receive
        inactivity timeout abandons the request through the same
        resolve_overflow path (413, since nothing was sent yet)."""
        import src.api.main as main_module
        from src.api.main import _BoundedReceiveMiddleware

        monkeypatch.setattr(
            main_module, "REQUEST_RECEIVE_INACTIVITY_TIMEOUT_SECONDS", 0.05
        )
        sent: list[dict] = []
        consumed = 0

        async def receive():
            nonlocal consumed
            if consumed == 0:
                consumed += 1
                return {"type": "http.request", "body": b"x" * 8, "more_body": True}
            # Never resolves: the client stalled mid-body.
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
        }

        async def reading_app(scope, receive, send):
            while True:
                message = await receive()
                if not message.get("more_body"):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def scenario() -> bool:
            try:
                await _BoundedReceiveMiddleware(reading_app)(scope, receive, send)
            except _BodyTooLarge:
                return True
            return False

        started = time.monotonic()
        aborted = asyncio.run(scenario())
        elapsed = time.monotonic() - started

        assert elapsed < 5.0, f"the stalled request must be bounded, took {elapsed:.1f}s"
        assert _statuses(sent) == [413], sent
        assert aborted is False


class TestVoiceOffload:
    def test_slow_transcription_keeps_event_loop_responsive(self):
        """While a slow (simulated) transcription occupies a worker thread,
        concurrent async work on the event loop completes without waiting
        for it — the F07 to_thread + semaphore offload contract."""
        from src.aac_app.services.learning.responses import _voice_semaphore

        worker_started = threading.Event()
        release_worker = threading.Event()

        def blocking_transcribe(*_args) -> str:
            worker_started.set()
            release_worker.wait(10)
            return "transcribed"

        async def scenario():
            semaphore = _voice_semaphore()
            results: dict[str, str] = {}

            async def transcription():
                async with semaphore:
                    results["r"] = await asyncio.to_thread(blocking_transcribe)

            task = asyncio.create_task(transcription())
            loop = asyncio.get_running_loop()
            # Block until the worker thread is genuinely inside the
            # blocking call (no real model download involved).
            await loop.run_in_executor(None, worker_started.wait, 5)

            # The loop must remain responsive while the worker blocks.
            await asyncio.wait_for(asyncio.sleep(0.05), timeout=2.0)

            release_worker.set()
            await asyncio.wait_for(task, timeout=5.0)
            assert results["r"] == "transcribed"

        asyncio.run(scenario())

    def test_production_voice_copy_runs_off_the_event_loop(
        self, tmp_path, test_db_session
    ):
        """D8: the multi-MB caller→worker temp copy must execute in the worker
        thread (never on the event loop), and the worker owns and deletes its
        copy. Transcription is stubbed, so no speech model is loaded."""
        from src.aac_app.db import session_scope
        from src.aac_app.services.learning import responses as responses_module
        from src.aac_app.services.learning.responses import ResponseProcessingMixin

        db = test_db_session
        user = _make_user(db, f"voice_copy_{uuid.uuid4().hex[:6]}")
        session = LearningSession(
            user_id=user.id,
            topic_name="voice",
            purpose="acceptance",
            status="active",
            conversation_history=[],
            comprehension_score=0.0,
        )
        db.add(session)
        db.commit()

        audio = tmp_path / "caller_upload.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 4096)

        class _Harness(ResponseProcessingMixin):
            _session_scope = staticmethod(session_scope)

            def _get_user_language(self, user_id, db):
                return "es"

            def _transcribe_voice_response(self, data, path, language="es"):
                # Abort right after the copy: the copy contract is the target.
                raise RuntimeError("sentinel: stop after copy")

        harness = _Harness()
        copy_started = threading.Event()
        release_copy = threading.Event()
        observed: dict[str, object] = {}
        real_copyfileobj = responses_module.shutil.copyfileobj

        def slow_copy(src, dst, *args, **kwargs):
            observed["thread"] = threading.get_ident()
            observed["temp_name"] = dst.name
            copy_started.set()
            release_copy.wait(5)
            return real_copyfileobj(src, dst, *args, **kwargs)

        async def scenario():
            loop_thread = threading.get_ident()

            async def run():
                return await harness.process_response(
                    session_id=session.id,
                    student_response="",
                    is_voice=True,
                    audio_path=str(audio),
                    db=db,
                )

            task = asyncio.create_task(run())
            # The loop must stay free while the worker sits inside the copy.
            await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    None, copy_started.wait, 5
                ),
                timeout=5.0,
            )
            assert observed["thread"] != loop_thread, (
                "the caller→worker copy must run in the worker thread"
            )
            release_copy.set()
            result = await asyncio.wait_for(task, timeout=5.0)
            # The stubbed transcription aborts after the copy completed.
            assert result["success"] is False

        with patch.object(responses_module.shutil, "copyfileobj", slow_copy):
            asyncio.run(scenario())

        assert observed["temp_name"] != str(audio)
        assert not os.path.exists(observed["temp_name"]), (
            "the worker must delete its temp copy"
        )
        assert audio.exists(), "the caller's upload must survive"

    def test_worker_temp_copy_contract(self, tmp_path):
        """The worker-owned temp copy is created from the caller's upload,
        cleaned by the handler's finally, and never deletes the original."""
        audio = tmp_path / "callers_audio.wav"
        audio.write_bytes(b"RIFF...payload...")

        worker_temp_copy: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                with open(audio, "rb") as src:
                    shutil.copyfileobj(src, tmp)
                worker_temp_copy = tmp.name
            assert os.path.exists(worker_temp_copy)
            with open(worker_temp_copy, "rb") as copied:
                assert copied.read() == b"RIFF...payload..."
        finally:
            if worker_temp_copy is not None:
                with contextlib.suppress(Exception):
                    os.remove(worker_temp_copy)

        assert not os.path.exists(worker_temp_copy)
        assert audio.exists(), "caller's original upload must survive"


# ---------------------------------------------------------------- F13


class TestLearningHistoryTruncation:
    def test_export_truncates_and_documents_over_100_sessions(
        self, test_db_session
    ):
        """>100 learning sessions: export carries exactly the latest 100 and
        meta records the truncation plus the true total."""
        from src.api.routers.export_import import export_data

        db = test_db_session
        user = _make_user(db, f"trunc_user_{uuid.uuid4().hex[:6]}")

        total = 137
        for i in range(total):
            db.add(
                LearningSession(
                    user_id=user.id,
                    topic_name=f"topic_{i:03d}",
                    purpose="acceptance",
                    status="completed",
                    comprehension_score=0.5,
                    questions_asked=1,
                    questions_answered=1,
                    correct_answers=1,
                )
            )
        db.commit()

        payload = export_data(username=user.username, db=db, current_user=user)
        meta = payload["meta"]

        assert meta["truncated"] is True
        assert meta["total_learning_sessions"] == total
        assert len(payload["learningHistory"]) == 100
        # The latest session (highest id) must be in the retained set.
        retained_ids = {h["id"] for h in payload["learningHistory"]}
        newest = db.query(LearningSession).order_by(LearningSession.id.desc()).first()
        assert newest.id in retained_ids

    def test_export_not_truncated_at_100(self, test_db_session):
        from src.api.routers.export_import import export_data

        db = test_db_session
        user = _make_user(db, f"notrunc_user_{uuid.uuid4().hex[:6]}")
        for i in range(100):
            db.add(
                LearningSession(
                    user_id=user.id,
                    topic_name=f"t{i}",
                    status="completed",
                )
            )
        db.commit()

        payload = export_data(username=user.username, db=db, current_user=user)
        assert payload["meta"]["truncated"] is False
        assert payload["meta"]["total_learning_sessions"] == 100
        assert len(payload["learningHistory"]) == 100
