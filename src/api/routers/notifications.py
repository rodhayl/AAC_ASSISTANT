import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.aac_app.db import create_session_factory, ensure_tables
from src.aac_app.models import Notification, User
from src.aac_app.services.notification_events import (
    publish_notification,
    subscribe,
    unsubscribe,
)
from src.api.deps import (
    get_current_active_user,
    get_current_admin_user,
    get_db,
    get_text,
    validate_active_token,
)
from src.api.schemas import NotificationCreate

router = APIRouter()


@router.get("/api/notifications/stream")
async def notifications_stream(token: str = None):
    # Authenticate with a short-lived session. The response stream is
    # intentionally unbounded, so it must not retain a request-scoped DB
    # session or connection for the lifetime of an SSE client.
    ensure_tables()
    db = create_session_factory()()
    try:
        user = validate_active_token(token, db)
        if not user:
            raise HTTPException(
                status_code=401, detail=get_text(key="errors.notifications.invalidToken")
            )
        user_id = user.id
    finally:
        db.rollback()
        db.close()


    async def event_generator():
        queue = subscribe(user_id)
        # Initial heartbeat to unblock clients. DB event delivery will be
        # connected before yielding so notifications cannot be missed.
        try:
            yield "data: {}\n\n"
            while True:
                try:
                    notification = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                else:
                    yield f"data: {json.dumps(notification)}\n\n"
        finally:
            unsubscribe(user_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/notifications")
def get_notifications(
    user_id: int,
    skip: int = Query(0, ge=0, le=100_000),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Fetch user notifications with pagination.
    """
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.notifications.unauthorizedView"
            ),
        )

    query = db.query(Notification).filter(Notification.user_id == user_id)

    if unread_only:
        query = query.filter(Notification.is_read.is_(False))

    total = query.count()
    notifications = (
        query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()
    )

    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.notification_type,
                "priority": n.priority,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "read_at": n.read_at.isoformat() if n.read_at else None,
            }
            for n in notifications
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/api/notifications")
@router.post("/api/notifications/")
def create_notification(
    notification: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Create a new notification for a user. (Admin only)
    """
    # Verify user exists
    user = db.query(User).filter(User.id == notification.user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.notifications.userNotFound"),
        )

    new_notification = Notification(
        user_id=notification.user_id,
        title=notification.title,
        message=notification.message,
        notification_type=notification.notification_type,
        priority=notification.priority,
        is_read=False,
    )
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)
    publish_notification(new_notification)

    return {
        "id": new_notification.id,
        "title": new_notification.title,
        "message": new_notification.message,
        "type": new_notification.notification_type,
        "priority": new_notification.priority,
        "is_read": new_notification.is_read,
        "created_at": (
            new_notification.created_at.isoformat()
            if new_notification.created_at
            else None
        ),
    }


@router.put("/api/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mark notification as read"""
    notification = (
        db.query(Notification).filter(Notification.id == notification_id).first()
    )
    if not notification:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.notifications.notFound"),
        )

    if notification.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.unauthorized"),
        )

    notification.is_read = True
    notification.read_at = datetime.now(UTC)
    db.commit()

    return {"ok": True}


@router.put("/api/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Mark all notifications as read for the authenticated user.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        Count of notifications marked as read
    """
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .update({"is_read": True, "read_at": datetime.now(UTC)})
    )
    db.commit()

    return {"ok": True, "count": count}


@router.delete("/api/notifications/{notification_id}")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete a notification.

    Args:
        notification_id: Notification ID
        db: Database session
        current_user: Authenticated user

    Returns:
        Success status
    """
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.notifications.notFound"),
        )

    # Verify ownership: user can only delete their own notifications (admins can delete any)
    if notification.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.unauthorized"),
        )

    db.delete(notification)
    db.commit()

    return {"ok": True}
