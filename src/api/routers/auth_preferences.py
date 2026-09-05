"""User preference endpoints associated with authentication and profiles."""

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import LearningMode, User, UserSettings
from src.api import schemas
from src.api.deps import (
    authorize_user_access,
    get_current_active_user,
    get_db,
    get_text,
)
from src.api.routers.auth_helpers import (
    build_preferences_response,
    update_user_settings,
    validate_preference_updates,
)

router = APIRouter()


def _get_authorized_preferences_user(
    db: Session, user_id: int, current_user: User
) -> User:
    """Fetch a preferences target user and enforce access authorization."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )
    authorize_user_access(
        target_user=target,
        current_user=current_user,
        db=db,
        forbidden_detail=get_text(
            user=current_user, key="errors.preferences.unauthorizedView"
        ),
    )
    return target


def _validate_default_learning_mode(
    db: Session,
    user_id: int,
    mode_key: str | None,
    current_user: User,
) -> None:
    """Ensure a saved default belongs to the target user's visible modes."""
    if mode_key is None:
        return
    mode = (
        db.query(LearningMode)
        .filter(LearningMode.key == mode_key)
        .filter(
            (LearningMode.created_by.is_(None))
            | (LearningMode.created_by == user_id)
        )
        .first()
    )
    if mode is None:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                key="errors.learningModes.defaultNotFound",
            ),
        )


@router.get("/preferences", response_model=schemas.UserPreferencesResponse)
def get_preferences(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get current user's preferences."""
    settings = (
        db.query(UserSettings)
        .filter(UserSettings.user_id == current_user.id)
        .first()
    )
    return build_preferences_response(settings)


@router.put("/preferences", response_model=schemas.UserPreferencesResponse)
def update_preferences(
    request: Request,
    prefs: schemas.UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update current user's preferences."""
    updates = prefs.model_dump(exclude_unset=True)
    validate_preference_updates(
        updates,
        user=current_user,
        accept_language=request.headers.get("accept-language"),
    )
    _validate_default_learning_mode(
        db,
        current_user.id,
        updates.get("default_learning_mode"),
        current_user,
    )
    settings = update_user_settings(db, current_user.id, updates)

    db.commit()
    db.refresh(settings)
    logger.info("Updated preferences for user {}", current_user.username)
    return build_preferences_response(settings)


@router.get(
    "/users/{user_id}/preferences",
    response_model=schemas.UserPreferencesResponse,
)
def get_user_preferences(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = _get_authorized_preferences_user(db, user_id, current_user)
    settings = db.query(UserSettings).filter(UserSettings.user_id == target.id).first()
    return build_preferences_response(settings)


@router.put(
    "/users/{user_id}/preferences",
    response_model=schemas.UserPreferencesResponse,
)
def update_user_preferences(
    request: Request,
    user_id: int,
    prefs: schemas.UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = _get_authorized_preferences_user(db, user_id, current_user)
    updates = prefs.model_dump(exclude_unset=True)
    validate_preference_updates(
        updates,
        user=current_user,
        accept_language=request.headers.get("accept-language"),
    )
    _validate_default_learning_mode(
        db,
        target.id,
        updates.get("default_learning_mode"),
        current_user,
    )
    settings = update_user_settings(db, target.id, updates)

    db.commit()
    db.refresh(settings)
    logger.info(
        "Updated preferences for user {} by {}",
        target.username,
        current_user.username,
    )
    return build_preferences_response(settings)
