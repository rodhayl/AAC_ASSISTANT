"""Reusable helpers for authentication routes."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.aac_app.models import UserSettings
from src.api import schemas

_F = TypeVar("_F", bound=Callable[..., Any])
_limiter_instance = Limiter(key_func=get_remote_address)


def conditional_limiter(rate: str) -> Callable[[_F], _F]:
    """Apply rate limiting in production while keeping tests deterministic."""

    def decorator(func: _F) -> _F:
        limited_func = _limiter_instance.limit(rate)(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if os.getenv("TESTING", "0") == "1":
                return func(*args, **kwargs)
            return limited_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email_format(email: str | None) -> None:
    """Reject a non-empty email that does not match the API's email contract."""
    if email and not _EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")


def validate_password_strength(password: str) -> None:
    """Require a non-empty password with length and character diversity."""
    if not password or len(password.strip()) == 0:
        raise HTTPException(status_code=400, detail="Password is required")
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long",
        )
    requirements = (
        (r"[A-Z]", "Password must contain at least one uppercase letter"),
        (r"[a-z]", "Password must contain at least one lowercase letter"),
        (r"[0-9]", "Password must contain at least one number"),
    )
    for pattern, message in requirements:
        if not re.search(pattern, password):
            raise HTTPException(status_code=400, detail=message)


def validate_preference_updates(updates: dict) -> None:
    """Reject negative timing preferences consistently across preference routes."""
    for key in ("dwell_time", "ignore_repeats"):
        value = updates.get(key)
        if value is not None and int(value) < 0:
            raise HTTPException(status_code=400, detail=f"{key} must be >= 0")


def build_preferences_response(
    settings: UserSettings | None,
) -> schemas.UserPreferencesResponse:
    """Convert persisted settings to the stable preferences API shape.

    Explicit defaults preserve compatibility with older databases where newer
    columns may be absent or nullable.
    """
    if settings is None:
        return schemas.UserPreferencesResponse()

    notifications_enabled = getattr(settings, "notifications_enabled", None)
    voice_mode_enabled = getattr(settings, "voice_mode_enabled", None)
    dark_mode = getattr(settings, "dark_mode", None)

    return schemas.UserPreferencesResponse(
        tts_voice=getattr(settings, "tts_voice", None) or "default",
        tts_language=getattr(settings, "tts_language", None),
        ui_language=getattr(settings, "ui_language", None),
        notifications_enabled=(
            notifications_enabled if notifications_enabled is not None else True
        ),
        voice_mode_enabled=voice_mode_enabled if voice_mode_enabled is not None else True,
        dark_mode=dark_mode if dark_mode is not None else False,
        dwell_time=int(getattr(settings, "dwell_time", 0) or 0),
        ignore_repeats=int(getattr(settings, "ignore_repeats", 0) or 0),
        high_contrast=bool(getattr(settings, "high_contrast", False) or False),
    )


def ensure_can_access_user_preferences(*, current_user, target_user, db) -> None:
    """Raise when a user cannot read or update another user's preferences."""
    if current_user.user_type == "admin":
        return
    if current_user.id == target_user.id:
        return
    if current_user.user_type == "teacher" and target_user.user_type == "student":
        from src.aac_app.models import StudentTeacher

        assigned = (
            db.query(StudentTeacher)
            .filter(
                StudentTeacher.teacher_id == current_user.id,
                StudentTeacher.student_id == target_user.id,
            )
            .first()
        )
        if assigned:
            return
    raise HTTPException(status_code=403, detail="Not authorized to access preferences")
