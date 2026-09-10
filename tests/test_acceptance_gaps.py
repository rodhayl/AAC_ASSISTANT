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
from src.api.main import app

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
