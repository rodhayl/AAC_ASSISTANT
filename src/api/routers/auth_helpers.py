"""Reusable helpers for authentication routes."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec

from fastapi import HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import User, UserSettings
from src.aac_app.services.auth_service import password_strength_error_key
from src.api import schemas
from src.api.deps import get_text

# Shared with the guardian-profiles router. guardian_profiles imports only
# src.api.deps + services (never auth_helpers), so this is acyclic.
from src.api.routers.guardian_profiles import enforce_locked_safety_fields

_P = ParamSpec("_P")
_limiter_instance = Limiter(key_func=get_remote_address)


def apply_student_safety_at_creation(
    db: Session,
    user: User,
    safety: schemas.StudentSafetyCreate | None,
    current_user: User,
) -> None:
    """Persist optional per-student safety configuration during creation.

    Creates (or fills) the student's guardian profile in the same transaction
    as the user row, so a student can be created with age, filter level,
    forbidden topics/trigger words and feature gates in one step — or without
    any of it, in which case the automatic age-based floor and admin global
    policy apply as usual. Teachers cannot override admin-locked fields;
    admins set the locks, so they can set anything.
    """
    if safety is None or user.user_type != "student":
        return
    from src.aac_app.models import GuardianProfile
    from src.aac_app.services import content_safety as safety_service

    level = safety.content_filter_level
    if level is not None and level not in safety_service.VALID_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user, key="errors.safety.invalidLevel"
            ),
        )

    constraints: dict[str, Any] = {
        "forbidden_topics": [
            str(term).strip()
            for term in (safety.forbidden_topics or [])
            if str(term).strip()
        ],
        "trigger_words": [
            str(term).strip()
            for term in (safety.trigger_words or [])
            if str(term).strip()
        ],
    }
    if level is not None:
        constraints["content_filter_level"] = level
    for key in safety_service.FEATURE_LOCKS:
        value = getattr(safety, key)
        if isinstance(value, bool):
            constraints[key] = value
    if safety.sentinel_moderation is not None:
        constraints["sentinel_moderation"] = safety.sentinel_moderation
    if safety.max_response_length is not None:
        constraints["max_response_length"] = safety.max_response_length

    enforce_locked_safety_fields(constraints, current_user)

    profile = db.query(GuardianProfile).filter_by(user_id=user.id).first()
    if profile is None:
        profile = GuardianProfile(
            user_id=user.id,
            created_by=current_user.id,
            template_name="default",
        )
        db.add(profile)
        db.flush()
    if safety.age is not None:
        profile.age = safety.age
    merged = dict(profile.safety_constraints or {})
    merged.update(constraints)
    profile.safety_constraints = merged
    profile.updated_by = current_user.id


def conditional_limiter(rate: str) -> Callable[[Callable[_P, Any]], Callable[_P, Any]]:
    """Apply rate limiting in production while keeping tests deterministic."""

    def decorator(func: Callable[_P, Any]) -> Callable[_P, Any]:
        limited_func = _limiter_instance.limit(rate)(func)

        @wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> Any:
            if os.getenv("TESTING", "0") == "1":
                return func(*args, **kwargs)
            return limited_func(*args, **kwargs)

        return wrapper

    return decorator


_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
SUPPORTED_UI_LANGUAGES = frozenset(
    value.strip() for value in config.SUPPORTED_UI_LANGUAGES.split(",") if value.strip()
)


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


def username_email_integrity_conflict(
    db: Session,
    username: str,
    email: str | None,
    *,
    accept_language: str | None = None,
    user: User | None = None,
    exclude_user_id: int | None = None,
) -> HTTPException:
    """Build the conflict response for a lost username/email insert race.

    Callers catch ``IntegrityError`` from the INSERT the pre-check
    (``ensure_username_email_available``) cannot fully guard, roll back, and
    raise this so a concurrent duplicate becomes the same 400/409 response
    the pre-check would have produced instead of an unhandled 500.

    ``exclude_user_id`` skips the edited row itself: an UPDATE path (email
    change) never alters its own username, so after the rollback that row
    still matches and would misreport an email conflict as a username one.
    """
    db.rollback()
    username_filters = [User.username == username]
    if exclude_user_id is not None:
        username_filters.append(User.id != exclude_user_id)
    if db.query(User).filter(*username_filters).first() is not None:
        return HTTPException(
            status_code=409,
            detail=get_text(
                user=user, accept_language=accept_language, key="errors.auth.usernameTaken"
            ),
        )
    if email and db.query(User).filter(User.email == email).first() is not None:
        return HTTPException(
            status_code=409,
            detail=get_text(
                user=user, accept_language=accept_language, key="errors.auth.emailTaken"
            ),
        )
    # The competing row is not visible to this session (e.g. still
    # uncommitted elsewhere); keep the fallback message stable and i18n'd
    # instead of a raw English literal.
    return HTTPException(
        status_code=409,
        detail=get_text(
            user=user,
            accept_language=accept_language,
            key="errors.auth.usernameOrEmailTaken",
        ),
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
    provider = updates.get("tts_provider")
    if provider is not None and provider not in {"browser", "kokoro"}:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=user,
                accept_language=accept_language,
                key="errors.preferences.unsupportedTtsProvider",
            ),
        )
    language = updates.get("ui_language")
    if language is not None and language not in SUPPORTED_UI_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=user,
                accept_language=accept_language,
                key="errors.settings.unsupportedLanguage",
            ),
        )
    for key in ("dwell_time", "ignore_repeats", "hover_speak_delay_ms"):
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
    tts_provider = getattr(settings, "tts_provider", None)
    ui_language = getattr(settings, "ui_language", None)

    def bounded_int(value: Any, default: int = 0) -> int:
        try:
            return min(max(int(value), 0), 2000)
        except (TypeError, ValueError):
            return default

    def bounded_speed(value: Any) -> float:
        # Legacy rows may keep NULL or garbage: clamp to the Kokoro range.
        try:
            return min(max(float(value), 0.5), 2.0)
        except (TypeError, ValueError):
            return 1.0

    def bounded_hover_delay(value: Any) -> int:
        # Clamp to the range the update schema accepts (see schemas.py);
        # legacy rows may keep NULL or out-of-range values.
        try:
            return min(max(int(value), 0), 5000)
        except (TypeError, ValueError):
            return 1000

    return schemas.UserPreferencesResponse(
        tts_provider=(
            tts_provider if tts_provider in {"browser", "kokoro"} else "kokoro"
        ),
        tts_voice=getattr(settings, "tts_voice", None) or "default",
        tts_local_voice=getattr(settings, "tts_local_voice", None) or "default",
        tts_local_speed=bounded_speed(getattr(settings, "tts_local_speed", 1.0)),
        tts_language=getattr(settings, "tts_language", None),
        # Legacy rows may keep NULL: preserve it (the frontend normalizes a
        # missing language to its default). Only an unsupported non-null value
        # is corrected so the select always shows a known option.
        ui_language=(
            ui_language if ui_language is None or ui_language in SUPPORTED_UI_LANGUAGES else "es-ES"
        ),
        notifications_enabled=(
            notifications_enabled if notifications_enabled is not None else True
        ),
        voice_mode_enabled=voice_mode_enabled if voice_mode_enabled is not None else True,
        dark_mode=dark_mode if dark_mode is not None else False,
        dwell_time=bounded_int(getattr(settings, "dwell_time", 0)),
        ignore_repeats=bounded_int(getattr(settings, "ignore_repeats", 0)),
        high_contrast=bool(getattr(settings, "high_contrast", False) or False),
        hover_speak_enabled=bool(getattr(settings, "hover_speak_enabled", False) or False),
        hover_speak_delay_ms=bounded_hover_delay(
            getattr(settings, "hover_speak_delay_ms", 1000)
        ),
        default_learning_mode=(
            getattr(settings, "default_learning_mode", None) or "practice"
        ),
    )
