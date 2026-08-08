"""User preference endpoints associated with authentication and profiles."""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import User, UserSettings
from src.api import schemas
from src.api.deps import get_current_active_user, get_db
from src.api.routers.auth_helpers import (
    build_preferences_response,
    ensure_can_access_user_preferences,
    validate_preference_updates,
)

router = APIRouter()


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
    settings = (
        db.query(UserSettings)
        .filter(UserSettings.user_id == current_user.id)
        .first()
    )
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    updates = prefs.model_dump(exclude_unset=True)
    validate_preference_updates(updates)
    for key, value in updates.items():
        setattr(settings, key, value)

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
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    ensure_can_access_user_preferences(
        current_user=current_user,
        target_user=target,
        db=db,
    )
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
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.user_type == "teacher" and target.user_type != "student":
        raise HTTPException(status_code=403, detail="Not authorized to update preferences")

    ensure_can_access_user_preferences(
        current_user=current_user,
        target_user=target,
        db=db,
    )
    settings = db.query(UserSettings).filter(UserSettings.user_id == target.id).first()
    if not settings:
        settings = UserSettings(user_id=target.id)
        db.add(settings)

    updates = prefs.model_dump(exclude_unset=True)
    validate_preference_updates(updates)
    for key, value in updates.items():
        setattr(settings, key, value)

    db.commit()
    db.refresh(settings)
    logger.info(
        "Updated preferences for user {} by {}",
        target.username,
        current_user.username,
    )
    return build_preferences_response(settings)
