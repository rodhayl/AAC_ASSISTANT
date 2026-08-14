"""User preference endpoints associated with authentication and profiles."""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import User, UserSettings
from src.api import schemas
from src.api.deps import authorize_user_access, get_current_active_user, get_db
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
        raise HTTPException(status_code=404, detail="User not found")
    authorize_user_access(
        target_user=target,
        current_user=current_user,
        db=db,
        forbidden_detail="Not authorized to access preferences",
    )
    return target


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
    prefs: schemas.UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update current user's preferences."""
    updates = prefs.model_dump(exclude_unset=True)
    validate_preference_updates(updates)
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
    user_id: int,
    prefs: schemas.UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = _get_authorized_preferences_user(db, user_id, current_user)
    updates = prefs.model_dump(exclude_unset=True)
    validate_preference_updates(updates)
    settings = update_user_settings(db, target.id, updates)

    db.commit()
    db.refresh(settings)
    logger.info(
        "Updated preferences for user {} by {}",
        target.username,
        current_user.username,
    )
    return build_preferences_response(settings)
