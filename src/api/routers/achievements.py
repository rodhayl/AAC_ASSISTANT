from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import Achievement, User, UserAchievement
from src.aac_app.services.achievement_system import AchievementSystem
from src.api import schemas
from src.api.deps import (
    get_achievement_system,
    get_current_active_user,
    get_db,
    get_text,
    verify_student_access,
)

router = APIRouter()


def _validate_criteria_pair(
    criteria_type: str | None,
    criteria_value: float | None,
    *,
    user: User,
) -> None:
    """Require automatic achievement criteria to be complete or absent."""
    if (criteria_type is None) != (criteria_value is None):
        raise HTTPException(
            status_code=400,
            detail=get_text(user=user, key="errors.achievements.criteriaIncomplete"),
        )


# ============== Categories Endpoint ==============

@router.get("/categories", response_model=list[str])
def get_categories(
    request: Request,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
):
    """Get all predefined achievement categories. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.viewCategories",
            ),
        )
    return system.get_categories()


@router.get("/criteria-types", response_model=list[str])
def get_criteria_types(
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """Get all available criteria types for achievements. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.viewCriteriaTypes",
            ),
        )
    return [
        "sessions_completed",
        "correct_answers",
        "comprehension_score",
        "vocabulary_size",
        "topics_completed",
        "consecutive_days",
        "voice_usage",
    ]


# ============== CRUD Endpoints for Achievement Management ==============

@router.get("", response_model=list[schemas.AchievementFullResponse])
@router.get("/", response_model=list[schemas.AchievementFullResponse])
def list_all_achievements(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all achievements (system + custom). Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.manage",
            ),
        )

    session = db
    achievements = (
        session.query(Achievement)
        .filter(Achievement.is_active)
        .all()
    )
    return [
        schemas.AchievementFullResponse(
            id=a.id,
            name=a.name,
            description=a.description or "",
            category=a.category or "general",
            points=a.points or 10,
            icon=a.icon or "🏆",
            is_manual=a.is_manual if hasattr(a, 'is_manual') and a.is_manual else False,
            created_by=a.created_by,
            target_user_id=a.target_user_id if hasattr(a, 'target_user_id') else None,
            is_active=a.is_active,
            created_at=a.created_at,
            criteria_type=a.criteria_type,
            criteria_value=a.criteria_value,
        )
        for a in achievements
    ]


@router.post("", response_model=schemas.AchievementFullResponse, status_code=201)
@router.post("/", response_model=schemas.AchievementFullResponse, status_code=201)
def create_achievement(
    request: Request,
    data: schemas.AchievementCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a custom achievement. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.create",
            ),
        )

    _validate_criteria_pair(
        data.criteria_type,
        data.criteria_value,
        user=current_user,
    )

    if data.target_user_id is not None:
        verify_student_access(
            data.target_user_id,
            current_user,
            db,
        )

    session = db
    # If criteria is provided, it's not manual. If no criteria, it's manual.
    has_criteria = (
        data.criteria_type is not None and data.criteria_value is not None
    )

    achievement = Achievement(
        name=data.name,
        description=data.description,
        category=data.category,
        points=data.points,
        icon=data.icon,
        created_by=current_user.id,
        target_user_id=data.target_user_id,
        is_manual=not has_criteria,
        criteria_type=data.criteria_type,
        criteria_value=data.criteria_value,
        is_active=True,
    )
    session.add(achievement)
    session.commit()
    session.refresh(achievement)

    logger.info(f"Created custom achievement '{data.name}' by user {current_user.id}")

    return schemas.AchievementFullResponse(
        id=achievement.id,
        name=achievement.name,
        description=achievement.description or "",
        category=achievement.category or "custom",
        points=achievement.points or 10,
        icon=achievement.icon or "🏆",
        is_manual=achievement.is_manual,
        created_by=achievement.created_by,
        target_user_id=achievement.target_user_id,
        is_active=achievement.is_active,
        created_at=achievement.created_at,
        criteria_type=achievement.criteria_type,
        criteria_value=achievement.criteria_value,
    )


@router.put("/{achievement_id}", response_model=schemas.AchievementFullResponse)
def update_achievement(
    request: Request,
    achievement_id: int,
    data: schemas.AchievementUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update an achievement. Only the creator or admin can update."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.update",
            ),
        )

    session = db
    achievement = session.get(Achievement, achievement_id)
    if not achievement:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.achievements.notFound"),
        )

    # Only creator or admin can update. System achievements have
    # created_by=None, so they always fail the ownership check for
    # teachers and are effectively admin-only; no separate branch needed.
    if achievement.created_by != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.updateOwnOnly",
            ),
        )

    if "target_user_id" in data.model_fields_set:
        if data.target_user_id is not None:
            verify_student_access(data.target_user_id, current_user, session)
        achievement.target_user_id = data.target_user_id

    # Update fields
    if data.name is not None:
        achievement.name = data.name
    if data.description is not None:
        achievement.description = data.description
    if data.category is not None:
        achievement.category = data.category
    if data.points is not None:
        achievement.points = data.points
    if data.icon is not None:
        achievement.icon = data.icon
    if data.is_active is not None:
        achievement.is_active = data.is_active

    # Update criteria when the client explicitly sends the fields. Checking
    # model_fields_set preserves the ability to clear an automatic
    # achievement back to a manual one by sending null values.
    if "criteria_type" in data.model_fields_set:
        achievement.criteria_type = data.criteria_type
    if "criteria_value" in data.model_fields_set:
        achievement.criteria_value = data.criteria_value

    # Recalculate is_manual based on presence of criteria. Reject a
    # partially specified pair rather than silently changing the award
    # type based on whichever field happened to be sent.
    _validate_criteria_pair(
        achievement.criteria_type,
        achievement.criteria_value,
        user=current_user,
    )
    has_criteria = (
        achievement.criteria_type is not None
        and achievement.criteria_value is not None
    )
    achievement.is_manual = not has_criteria

    session.commit()
    session.refresh(achievement)

    logger.info(f"Updated achievement {achievement_id} by user {current_user.id}")

    return schemas.AchievementFullResponse(
        id=achievement.id,
        name=achievement.name,
        description=achievement.description or "",
        category=achievement.category or "general",
        points=achievement.points or 10,
        icon=achievement.icon or "🏆",
        is_manual=achievement.is_manual if hasattr(achievement, 'is_manual') else False,
        created_by=achievement.created_by,
        target_user_id=achievement.target_user_id if hasattr(achievement, 'target_user_id') else None,
        is_active=achievement.is_active,
        created_at=achievement.created_at,
        criteria_type=achievement.criteria_type,
        criteria_value=achievement.criteria_value,
    )


@router.delete("/{achievement_id}", status_code=204)
def delete_achievement(
    request: Request,
    achievement_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a custom achievement. Only the creator or admin can delete."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.delete",
            ),
        )

    session = db
    achievement = session.get(Achievement, achievement_id)
    if not achievement:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.achievements.notFound"),
        )

    # System achievements cannot be deleted
    if achievement.created_by is None:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.cannotDeleteSystem",
            ),
        )

    # Only creator or admin can delete
    if achievement.created_by != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.deleteOwnOnly",
            ),
        )

    # Delete associated user achievements first
    session.query(UserAchievement).filter(
        UserAchievement.achievement_id == achievement_id
    ).delete()

    session.delete(achievement)
    session.commit()

    logger.info(f"Deleted achievement {achievement_id} by user {current_user.id}")

    return None


@router.post("/{achievement_id}/award", response_model=schemas.AchievementResponse)
def award_achievement(
    request: Request,
    achievement_id: int,
    data: schemas.AchievementAward,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Manually award an achievement to a user. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.award",
            ),
        )

    session = db
    achievement = session.get(Achievement, achievement_id)
    if not achievement:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.achievements.notFound"),
        )

    # Only award achievements to an existing student the actor can access.
    # This prevents teachers from targeting unrelated users or non-students.
    verify_student_access(data.user_id, current_user, session)

    # Check if user already has this achievement
    existing = (
        session.query(UserAchievement)
        .filter(
            UserAchievement.user_id == data.user_id,
            UserAchievement.achievement_id == achievement_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                accept_language=request.headers.get("accept-language"),
                key="errors.achievements.alreadyAwarded",
            ),
        )

    # Award the achievement
    user_achievement = UserAchievement(
        user_id=data.user_id,
        achievement_id=achievement_id,
        earned_at=datetime.now(),
        progress=1.0,
    )
    session.add(user_achievement)
    session.commit()

    logger.info(
        f"Awarded achievement {achievement_id} to user {data.user_id} by {current_user.id}"
    )

    return schemas.AchievementResponse(
        name=achievement.name,
        description=achievement.description or "",
        category=achievement.category or "general",
        points=achievement.points or 10,
        icon=achievement.icon or "🏆",
        earned_at=user_achievement.earned_at.isoformat(),
        progress=1.0,
    )


# ============== Existing User Achievement Endpoints ==============

@router.get("/user/{user_id}", response_model=list[schemas.AchievementResponse])
def get_user_achievements(
    user_id: int,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get all achievements for a user"""
    if user_id != current_user.id:
        verify_student_access(
            user_id,
            current_user,
            db,
        )

    return system.get_user_achievements(user_id, db=db)


@router.post("/user/{user_id}/check", response_model=list[schemas.AchievementResponse])
def check_achievements(
    user_id: int,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Check and award new achievements for a user"""
    if user_id != current_user.id:
        verify_student_access(
            user_id,
            current_user,
            db,
        )

    # Check for new achievements first to trigger awarding
    system.check_achievements(user_id, db=db)
    # Commit the awards before responding: the request dependency's teardown
    # commit runs after the response is sent, and the UI typically re-reads
    # the achievement list immediately after this check.
    db.commit()

    # Return the full list of user achievements with earned_at timestamps
    return system.get_user_achievements(user_id, db=db)


@router.get("/user/{user_id}/points", response_model=int)
def get_user_points(
    user_id: int,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get total points for a user"""
    if user_id != current_user.id:
        verify_student_access(
            user_id,
            current_user,
            db,
        )

    return system.get_user_points(user_id, db=db)


@router.get("/leaderboard", response_model=list[schemas.LeaderboardEntry])
def get_leaderboard(
    limit: int = Query(10, ge=1, le=100),
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get leaderboard"""
    # Leaderboard is generally public for authenticated users
    return system.get_leaderboard(limit, db=db)

