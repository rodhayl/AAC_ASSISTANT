from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from src.aac_app.models.database import Achievement, User, UserAchievement, get_session
from src.aac_app.services.achievement_system import AchievementSystem
from src.api import schemas
from src.api.dependencies import (
    get_achievement_system,
    get_current_active_user,
    get_text,
)

router = APIRouter()


# ============== Categories Endpoint ==============

@router.get("/categories", response_model=List[str])
def get_categories(
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
):
    """Get all predefined achievement categories. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can view categories",
        )
    return system.get_categories()


@router.get("/criteria-types", response_model=List[str])
def get_criteria_types(
    current_user: User = Depends(get_current_active_user),
):
    """Get all available criteria types for achievements. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can view criteria types",
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

@router.get("/", response_model=List[schemas.AchievementFullResponse])
def list_all_achievements(
    current_user: User = Depends(get_current_active_user),
):
    """List all achievements (system + custom). Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can manage achievements",
        )

    with get_session() as session:
        achievements = (
            session.query(Achievement)
            .filter(Achievement.is_active == True)
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


@router.post("/", response_model=schemas.AchievementFullResponse, status_code=201)
def create_achievement(
    data: schemas.AchievementCreate,
    current_user: User = Depends(get_current_active_user),
):
    """Create a custom achievement. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can create achievements",
        )

    with get_session() as session:
        # If criteria is provided, it's not manual. If no criteria, it's manual.
        has_criteria = bool(data.criteria_type and data.criteria_value)
        
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
    achievement_id: int,
    data: schemas.AchievementUpdate,
    current_user: User = Depends(get_current_active_user),
):
    """Update an achievement. Only the creator or admin can update."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can update achievements",
        )

    with get_session() as session:
        achievement = session.get(Achievement, achievement_id)
        if not achievement:
            raise HTTPException(status_code=404, detail="Achievement not found")

        # Only creator or admin can update
        if achievement.created_by != current_user.id and current_user.user_type != "admin":
            raise HTTPException(
                status_code=403,
                detail="You can only update achievements you created",
            )

        # System achievements (created_by=None) can only be updated by admin
        if achievement.created_by is None and current_user.user_type != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only admins can update system achievements",
            )

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
        
        # Update criteria if provided
        if data.criteria_type is not None:
            achievement.criteria_type = data.criteria_type
        if data.criteria_value is not None:
            achievement.criteria_value = data.criteria_value
            
        # Recalculate is_manual based on presence of criteria
        has_criteria = bool(achievement.criteria_type and achievement.criteria_value)
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
    achievement_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """Delete a custom achievement. Only the creator or admin can delete."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can delete achievements",
        )

    with get_session() as session:
        achievement = session.get(Achievement, achievement_id)
        if not achievement:
            raise HTTPException(status_code=404, detail="Achievement not found")

        # System achievements cannot be deleted
        if achievement.created_by is None:
            raise HTTPException(
                status_code=403,
                detail="System achievements cannot be deleted",
            )

        # Only creator or admin can delete
        if achievement.created_by != current_user.id and current_user.user_type != "admin":
            raise HTTPException(
                status_code=403,
                detail="You can only delete achievements you created",
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
    achievement_id: int,
    data: schemas.AchievementAward,
    current_user: User = Depends(get_current_active_user),
):
    """Manually award an achievement to a user. Teachers/admins only."""
    if current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can award achievements",
        )

    with get_session() as session:
        achievement = session.get(Achievement, achievement_id)
        if not achievement:
            raise HTTPException(status_code=404, detail="Achievement not found")

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
                detail="User already has this achievement",
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

@router.get("/user/{user_id}", response_model=List[schemas.AchievementResponse])
def get_user_achievements(
    user_id: int,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
):
    """Get all achievements for a user"""
    if user_id != current_user.id and current_user.user_type not in ["teacher", "admin"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.achievements.unauthorizedView"
            ),
        )

    return system.get_user_achievements(user_id)


@router.post("/user/{user_id}/check", response_model=List[schemas.AchievementResponse])
def check_achievements(
    user_id: int,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
):
    """Check and award new achievements for a user"""
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.achievements.unauthorizedCheck"
            ),
        )

    # Check for new achievements first to trigger awarding
    system.check_achievements(user_id)

    # Return the full list of user achievements with earned_at timestamps
    return system.get_user_achievements(user_id)


@router.get("/user/{user_id}/points", response_model=int)
def get_user_points(
    user_id: int,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
):
    """Get total points for a user"""
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.achievements.unauthorizedViewPoints"
            ),
        )

    return system.get_user_points(user_id)


@router.get("/leaderboard", response_model=List[schemas.LeaderboardEntry])
def get_leaderboard(
    limit: int = 10,
    system: AchievementSystem = Depends(get_achievement_system),
    current_user: User = Depends(get_current_active_user),
):
    """Get leaderboard"""
    # Leaderboard is generally public for authenticated users
    return system.get_leaderboard(limit)

