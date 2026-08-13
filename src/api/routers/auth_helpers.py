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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.aac_app.models import UserSettings
from src.aac_app.services.auth_service import password_strength_error
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
    error = password_strength_error(password)
    if error:
        raise HTTPException(status_code=400, detail=error)


def validate_preference_updates(updates: dict) -> None:
    """Reject negative timing preferences consistently across preference routes."""
    for key in ("dwell_time", "ignore_repeats"):
        value = updates.get(key)
        if value is not None and int(value) < 0:
            raise HTTPException(status_code=400, detail=f"{key} must be >= 0")


def update_user_settings(
    db: Session,
    user_id: int,
    updates: dict[str, Any],
) -> UserSettings:
    """Update one user's settings, tolerating concurrent first-write races.

    Preference updates can arrive through both the authentication preferences
    route and the UI-language route at the same time. Since ``user_id`` is
    unique, two requests that both observe a missing row can race on INSERT.
    Flush the new row early; if another request wins, roll back only this
    request's failed transaction, reload the winner, and apply the update.
    """
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings is None:
        try:
            # Keep the insert inside a savepoint so a concurrent unique-key
            # winner cannot roll back unrelated work in the caller's session.
            with db.begin_nested():
                settings = UserSettings(user_id=user_id)
                db.add(settings)
                db.flush()
        except IntegrityError:
            settings = (
                db.query(UserSettings)
                .filter(UserSettings.user_id == user_id)
                .first()
            )
            if settings is None:
                raise

    for key, value in updates.items():
        setattr(settings, key, value)
    return settings


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
