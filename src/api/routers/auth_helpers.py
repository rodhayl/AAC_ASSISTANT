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

from src.aac_app.models import User, UserSettings
from src.aac_app.services.auth_service import password_strength_error_key
from src.api import schemas
from src.api.deps import get_text

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


def validate_email_format(
    email: str | None,
    *,
    accept_language: str | None = None,
    user: User | None = None,
) -> None:
    """Reject a non-empty email that does not match the API's email contract."""
    if email and not _EMAIL_PATTERN.match(email):
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=user, accept_language=accept_language, key="errors.auth.emailInvalid"
            ),
        )


def validate_password_strength(
    password: str,
    *,
    accept_language: str | None = None,
    user: User | None = None,
) -> None:
    """Require a non-empty password with length and character diversity."""
    key = password_strength_error_key(password)
    if key:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=user, accept_language=accept_language, key=key),
        )


def ensure_username_email_available(
    db: Session,
    username: str,
    email: str | None,
    *,
    accept_language: str | None = None,
    user: User | None = None,
) -> None:
    """Reject registration when the username or a provided email is taken."""
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=user, accept_language=accept_language, key="errors.auth.usernameTaken"
            ),
        )
    if email:
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail=get_text(
                    user=user, accept_language=accept_language, key="errors.auth.emailTaken"
                ),
            )


def validate_preference_updates(
    updates: dict,
    *,
    accept_language: str | None = None,
    user: User | None = None,
) -> None:
    """Reject negative timing preferences consistently across preference routes."""
    for key in ("dwell_time", "ignore_repeats"):
        value = updates.get(key)
        if value is not None and int(value) < 0:
            raise HTTPException(
                status_code=400,
                detail=get_text(
                    user=user,
                    accept_language=accept_language,
                    key="errors.preferences.mustBeNonNegative",
                    field=key,
                ),
            )


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
