import asyncio
import json
from datetime import datetime

import pytest

from src.aac_app.models import LearningSession, Notification, User
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.auth_service import get_password_hash
from src.api.routers.notifications import create_notification, notifications_stream
from src.api.schemas import NotificationCreate


async def _read_stream_event(stream, publish):
    stream = await stream
    iterator = stream.body_iterator
    try:
        heartbeat = await asyncio.wait_for(anext(iterator), timeout=1)
        assert heartbeat == "data: {}\n\n"
        publish()
        raw_event = await asyncio.wait_for(anext(iterator), timeout=1)
        assert raw_event.startswith("data: ")
        return json.loads(raw_event.removeprefix("data: ").strip())
    finally:
        await iterator.aclose()


def test_admin_notification_is_delivered_to_subscriber(
    setup_test_db,
    test_db_session,
    admin_user,
    regular_user,
    admin_token,
    user_token,
):
    stream = notifications_stream(token=user_token, db=test_db_session)

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

    event = asyncio.run(_read_stream_event(stream, publish))

    assert event["title"] == "New board"
    assert event["type"] == "info"
    assert event["is_read"] is False


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
    stream_a = notifications_stream(token=admin_token, db=test_db_session)
    stream_b = notifications_stream(token=other_token, db=test_db_session)

    async def read_isolated_events():
        stream_a_response = await stream_a
        stream_b_response = await stream_b
        iterator_a = stream_a_response.body_iterator
        iterator_b = stream_b_response.body_iterator
        try:
            assert await anext(iterator_a) == "data: {}\n\n"
            assert await anext(iterator_b) == "data: {}\n\n"

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
                (await asyncio.wait_for(anext(iterator_a), timeout=1))
                .removeprefix("data: ")
                .strip()
            )
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(anext(iterator_b), timeout=0.05)
            return admin_event
        finally:
            await iterator_a.aclose()
            await iterator_b.aclose()

    event = asyncio.run(read_isolated_events())

    assert event["title"] == "Admin-only"


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

    stream = notifications_stream(token=user_token, db=test_db_session)

    def award():
        newly_earned = AchievementSystem().check_achievements(
            regular_user.id,
            db=test_db_session,
        )
        assert any(achievement["name"] == "First Steps" for achievement in newly_earned)

    event = asyncio.run(_read_stream_event(stream, award))
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
