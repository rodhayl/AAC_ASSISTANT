import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.aac_app.models import LearningSession, Notification, User
from src.aac_app.services import notification_events
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.notification_events import (
    SUBSCRIBER_QUEUE_MAXSIZE,
    publish_notification,
    subscribe,
    unsubscribe,
)
from src.api.main import app
from src.api.routers.notifications import create_notification
from src.api.schemas import NotificationCreate


async def _read_stream_event(stream, publish):
    try:
        heartbeat = await asyncio.wait_for(stream.next_body(), timeout=1)
        assert heartbeat == b"data: {}\n\n"
        publish()
        raw_event = await asyncio.wait_for(stream.next_body(), timeout=1)
        assert raw_event.startswith(b"data: ")
        return json.loads(raw_event.removeprefix(b"data: ").strip())
    finally:
        await stream.close()


class _ASGIStream:
    """Small ASGI client that exposes individual StreamingResponse chunks."""

    def __init__(self, token: str):
        self.messages = asyncio.Queue()
        self.disconnect = asyncio.Event()
        self._request_sent = False
        self.task = asyncio.create_task(self._run(token))

    async def _run(self, token: str):
        async def receive():
            if not self._request_sent:
                self._request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self.disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            await self.messages.put(message)

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/notifications/stream",
            "raw_path": b"/api/notifications/stream",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"authorization", f"Bearer {token}".encode()),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
        await app(scope, receive, send)

    async def next_body(self) -> bytes:
        message = await self.messages.get()
        if message["type"] == "http.response.start":
            message = await self.messages.get()
        assert message["type"] == "http.response.body"
        return message["body"]

    async def close(self):
        self.disconnect.set()
        await self.task


def test_admin_notification_is_delivered_to_subscriber(
    setup_test_db,
    test_db_session,
    admin_user,
    regular_user,
    admin_token,
    user_token,
):
    def publish():
        created = create_notification(
            notification=NotificationCreate(
                user_id=regular_user.id,
                title="New board",
                message="A board was assigned to you.",
                notification_type="info",
                priority="normal",
            ),
            db=test_db_session,
            current_user=admin_user,
        )
        assert created["title"] == "New board"

    async def exercise():
        return await _read_stream_event(_ASGIStream(user_token), publish)

    event = asyncio.run(exercise())

    assert event["title"] == "New board"
    assert event["type"] == "info"
    assert event["is_read"] is False


def test_inactive_user_cannot_open_notification_stream(
    setup_test_db,
    test_db_session,
):
    inactive_user = User(
        username="inactive_notification_user",
        email="inactive-notification@test.com",
        password_hash=get_password_hash("FakeNotificationPassword123"),
        display_name="Inactive Notification User",
        user_type="student",
        is_active=False,
    )
    test_db_session.add(inactive_user)
    test_db_session.commit()

    from src.aac_app.utils.jwt_utils import create_access_token

    token = create_access_token(
        data={
            "sub": inactive_user.username,
            "user_id": inactive_user.id,
            "user_type": inactive_user.user_type,
        }
    )

    async def exercise():
        stream = _ASGIStream(token)
        try:
            response_start = await asyncio.wait_for(stream.messages.get(), timeout=1)
            assert response_start["type"] == "http.response.start"
            assert response_start["status"] == 401
        finally:
            await stream.close()

    asyncio.run(exercise())


def test_notification_stream_is_isolated_per_user(
    setup_test_db,
    test_db_session,
    admin_user,
    regular_user,
    admin_token,
):
    other_user = User(
        username="other_notification_user",
        email="other-notification@test.com",
        password_hash=get_password_hash("FakeNotificationPassword123"),
        display_name="Other Notification User",
        user_type="student",
        is_active=True,
    )
    test_db_session.add(other_user)
    test_db_session.commit()

    from src.aac_app.utils.jwt_utils import create_access_token

    other_token = create_access_token(
        data={
            "sub": other_user.username,
            "user_id": other_user.id,
            "user_type": other_user.user_type,
        }
    )
    async def read_isolated_events():
        stream_a = _ASGIStream(admin_token)
        stream_b = _ASGIStream(other_token)
        try:
            assert await stream_a.next_body() == b"data: {}\n\n"
            assert await stream_b.next_body() == b"data: {}\n\n"

            created = create_notification(
                notification=NotificationCreate(
                    user_id=admin_user.id,
                    title="Admin-only",
                    message="Only the admin should receive this.",
                    notification_type="info",
                    priority="normal",
                ),
                db=test_db_session,
                current_user=admin_user,
            )
            assert created["title"] == "Admin-only"
            admin_event = json.loads(
                (await asyncio.wait_for(stream_a.next_body(), timeout=1))
                .removeprefix(b"data: ")
                .strip()
            )
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(stream_b.next_body(), timeout=0.05)
            return admin_event
        finally:
            await stream_a.close()
            await stream_b.close()

    event = asyncio.run(read_isolated_events())

    assert event["title"] == "Admin-only"


def test_asgi_stream_lifecycle_connect_event_disconnect_cleanup(
    setup_test_db,
    test_db_session,
    admin_user,
    regular_user,
    user_token,
):
    async def exercise():
        stream = _ASGIStream(user_token)
        try:
            assert await stream.next_body() == b"data: {}\n\n"
            created = create_notification(
                notification=NotificationCreate(
                    user_id=regular_user.id,
                    title="ASGI event",
                    message="StreamingResponse delivered this event.",
                    notification_type="info",
                    priority="normal",
                ),
                db=test_db_session,
                current_user=admin_user,
            )
            event = json.loads(
                (await stream.next_body()).removeprefix(b"data: ").strip()
            )
            assert event == {
                "id": created["id"],
                "title": "ASGI event",
                "message": "StreamingResponse delivered this event.",
                "type": "info",
                "priority": "normal",
                "is_read": False,
                "created_at": event["created_at"],
                "read_at": None,
            }
            assert event["created_at"] is not None
            assert created["title"] == "ASGI event"
        finally:
            await stream.close()

    asyncio.run(exercise())
    assert regular_user.id not in notification_events._subscribers


def test_asgi_streams_keep_concurrent_subscribers_isolated(
    setup_test_db,
    test_db_session,
    admin_user,
    regular_user,
    admin_token,
):
    other_user = User(
        username="asgi_other_notification_user",
        email="asgi-other-notification@test.com",
        password_hash=get_password_hash("FakeNotificationPassword123"),
        display_name="ASGI Other Notification User",
        user_type="student",
        is_active=True,
    )
    test_db_session.add(other_user)
    test_db_session.commit()

    from src.aac_app.utils.jwt_utils import create_access_token

    other_token = create_access_token(
        data={
            "sub": other_user.username,
            "user_id": other_user.id,
            "user_type": other_user.user_type,
        }
    )

    async def exercise():
        admin_stream = _ASGIStream(admin_token)
        other_stream = _ASGIStream(other_token)
        try:
            assert await admin_stream.next_body() == b"data: {}\n\n"
            assert await other_stream.next_body() == b"data: {}\n\n"

            create_notification(
                notification=NotificationCreate(
                    user_id=admin_user.id,
                    title="Admin ASGI event",
                    message="Only the admin stream receives this.",
                    notification_type="info",
                    priority="normal",
                ),
                db=test_db_session,
                current_user=admin_user,
            )
            await asyncio.sleep(0)
            admin_event = json.loads(
                (await admin_stream.next_body()).removeprefix(b"data: ").strip()
            )
            assert admin_event["title"] == "Admin ASGI event"
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(other_stream.next_body(), timeout=0.05)
        finally:
            await admin_stream.close()
            await other_stream.close()

    asyncio.run(exercise())

    assert admin_user.id not in notification_events._subscribers
    assert other_user.id not in notification_events._subscribers


def test_achievement_award_persists_notification_and_delivers_event(
    setup_test_db,
    test_db_session,
    regular_user,
    user_token,
):
    completed_session = LearningSession(
        user_id=regular_user.id,
        topic_name="animals",
        status="completed",
        comprehension_score=1.0,
        questions_answered=1,
        correct_answers=1,
        started_at=datetime.now(),
    )
    test_db_session.add(completed_session)
    test_db_session.commit()

    def award():
        newly_earned = AchievementSystem().check_achievements(
            regular_user.id,
            db=test_db_session,
        )
        assert any(achievement["name"] == "First Steps" for achievement in newly_earned)
        test_db_session.commit()

    async def exercise():
        return await _read_stream_event(_ASGIStream(user_token), award)

    event = asyncio.run(exercise())
    notification = (
        test_db_session.query(Notification)
        .filter(
            Notification.user_id == regular_user.id,
            Notification.notification_type == "achievement",
            Notification.title == "Achievement Unlocked",
            Notification.message.like("First Steps%"),
        )
        .one()
    )

    assert event["title"] == "Achievement Unlocked"
    assert event["type"] == "achievement"
    assert event["is_read"] is False
    assert notification.is_read is False


def test_subscriber_queue_drops_oldest_event_when_full():
    async def exercise():
        queue = subscribe(1)
        try:
            loop = asyncio.get_running_loop()
            with patch.object(loop, "call_soon_threadsafe", wraps=loop.call_soon_threadsafe) as schedule:
                for notification_id in range(SUBSCRIBER_QUEUE_MAXSIZE + 1):
                    publish_notification(
                        SimpleNamespace(
                            id=notification_id,
                            user_id=1,
                            title=f"Notification {notification_id}",
                            message="message",
                            notification_type="info",
                            priority="normal",
                            is_read=False,
                            created_at=None,
                            read_at=None,
                        )
                    )
                assert schedule.call_count == 1

            # publish_notification schedules queue writes on the subscriber's
            # loop, so yield once to let all callbacks run.
            await asyncio.sleep(0)

            assert queue.maxsize == SUBSCRIBER_QUEUE_MAXSIZE
            assert queue.dropped_count == 1
            pending_ids = [
                (await queue.get())["id"] for _ in range(SUBSCRIBER_QUEUE_MAXSIZE)
            ]
            assert pending_ids[0] == 1
            assert pending_ids[-1] == SUBSCRIBER_QUEUE_MAXSIZE
        finally:
            unsubscribe(1, queue)

    asyncio.run(exercise())


def test_achievement_notification_is_discarded_when_transaction_rolls_back(
    setup_test_db,
    test_db_session,
    regular_user,
    user_token,
):
    completed_session = LearningSession(
        user_id=regular_user.id,
        topic_name="rollback",
        status="completed",
        comprehension_score=1.0,
        questions_answered=1,
        correct_answers=1,
        started_at=datetime.now(),
    )
    test_db_session.add(completed_session)
    test_db_session.commit()

    async def exercise():
        stream = _ASGIStream(user_token)
        try:
            assert await stream.next_body() == b"data: {}\n\n"
            newly_earned = AchievementSystem().check_achievements(
                regular_user.id,
                db=test_db_session,
            )
            assert any(achievement["name"] == "First Steps" for achievement in newly_earned)
            test_db_session.rollback()

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(stream.next_body(), timeout=0.05)
        finally:
            await stream.close()

    asyncio.run(exercise())

    assert (
        test_db_session.query(Notification)
        .filter(Notification.user_id == regular_user.id)
        .count()
        == 0
    )
