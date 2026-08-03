"""In-process delivery of persisted notifications to SSE subscribers."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class _Subscriber:
    """An SSE queue and the event loop that owns it."""

    queue: asyncio.Queue[dict[str, Any]]
    loop: asyncio.AbstractEventLoop


_subscribers: dict[int, set[_Subscriber]] = {}
_subscriber_lock = RLock()


def subscribe(user_id: int) -> asyncio.Queue[dict[str, Any]]:
    """Register an SSE queue for a user and return it to the stream."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    with _subscriber_lock:
        _subscribers.setdefault(user_id, set()).add(_Subscriber(queue, loop))
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Remove an SSE queue when its stream disconnects."""
    with _subscriber_lock:
        subscribers = _subscribers.get(user_id)
        if not subscribers:
            return

        stale_subscribers = {
            subscriber
            for subscriber in tuple(subscribers)
            if subscriber.queue is queue
        }
        subscribers.difference_update(stale_subscribers)
        if not subscribers:
            _subscribers.pop(user_id, None)


def notification_payload(notification: Any) -> dict[str, Any]:
    """Convert a notification ORM object into the public SSE payload."""
    return {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "type": notification.notification_type,
        "priority": notification.priority,
        "is_read": notification.is_read,
        "created_at": _isoformat(notification.created_at),
        "read_at": _isoformat(notification.read_at),
    }


def publish_notification(notification: Any) -> None:
    """Publish a persisted notification to all subscribers for its user."""
    event = notification_payload(notification)
    with _subscriber_lock:
        subscribers = tuple(_subscribers.get(notification.user_id, ()))

    for subscriber in subscribers:
        try:
            subscriber.loop.call_soon_threadsafe(
                subscriber.queue.put_nowait,
                event,
            )
        except RuntimeError:
            # The stream's loop has already shut down. Its generator cleanup
            # will remove the stale subscriber when possible.
            with _subscriber_lock:
                _subscribers.get(notification.user_id, set()).discard(subscriber)


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
