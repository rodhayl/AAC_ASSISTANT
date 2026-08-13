from contextlib import nullcontext
from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload

from ..db import get_session
from ..models import (
    Achievement,
    LearningSession,
    Notification,
    User,
    UserAchievement,
    UserProgress,
)
from .achievement_catalog import PREDEFINED_ACHIEVEMENTS
from .notification_events import stage_notification


class AchievementSystem:
    """Gamification and achievement system for AAC learning"""

    def __init__(self):
        self.achievements = self._initialize_achievements()
        logger.info("Achievement system initialized")

    def _initialize_achievements(self) -> dict[str, dict]:
        """Return a per-instance copy of the predefined catalog."""
        return {key: values.copy() for key, values in PREDEFINED_ACHIEVEMENTS.items()}

    def check_achievements(
        self, user_id: int, db: Session | None = None
    ) -> list[dict]:
        """Check and award achievements for a user"""
        logger.info(f"Checking achievements for user {user_id}")

        if db is not None:
            return self._check_achievements_in_session(user_id, db)

        try:
            with get_session() as session:
                return self._check_achievements_in_session(user_id, session)
        except Exception as exc:
            logger.error(f"Failed to check achievements for user {user_id}: {exc}")
            return []

    def _check_achievements_in_session(
        self, user_id: int, session: Session
    ) -> list[dict]:
        """Check achievements using the caller's transaction."""
        newly_earned = []
        user = session.get(User, user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return []

        stats = self._get_user_stats(user_id, session)
        for achievement_key, achievement_data in self.achievements.items():
            if self._check_achievement_criteria(
                user_id, achievement_data, stats, session
            ):
                earned = self._award_achievement(user_id, achievement_key, session)
                if earned:
                    newly_earned.append(achievement_data)

        session.flush()
        if newly_earned:
            logger.success(
                f"Awarded {len(newly_earned)} new achievements to user {user_id}"
            )
        return newly_earned

    def _get_user_stats(self, user_id: int, session) -> dict[str, Any]:
        """Get comprehensive user statistics with bounded database reads."""
        completed_filter = (
            LearningSession.user_id == user_id,
            LearningSession.status == "completed",
        )
        aggregates = (
            session.query(
                func.count(LearningSession.id).label("sessions_completed"),
                func.coalesce(func.sum(LearningSession.questions_answered), 0).label(
                    "total_questions_answered"
                ),
                func.coalesce(func.sum(LearningSession.correct_answers), 0).label(
                    "total_correct_answers"
                ),
                (
                    func.count(func.distinct(LearningSession.topic_name))
                    + func.coalesce(
                        func.max(
                            case(
                                (LearningSession.topic_name.is_(None), 1),
                                else_=0,
                            )
                        ),
                        0,
                    )
                ).label("topics_completed"),
                func.avg(
                    case(
                        (LearningSession.comprehension_score > 0, LearningSession.comprehension_score),
                        else_=None,
                    )
                ).label("average_comprehension"),
            )
            .filter(*completed_filter)
            .one()
        )

        # Only positive comprehension scores contributed to the former Python
        # average. Keep that rule in SQL so large histories do not cross the
        # application/database boundary as full ORM rows.
        stats = {
            "sessions_completed": int(aggregates.sessions_completed or 0),
            "total_questions_answered": int(aggregates.total_questions_answered or 0),
            "total_correct_answers": int(aggregates.total_correct_answers or 0),
            "topics_completed": int(aggregates.topics_completed or 0),
            "average_comprehension": float(aggregates.average_comprehension or 0),
        }

        # Streak calculation still needs ordered dates, but the database returns
        # one small scalar row per active day instead of every learning session.
        date_rows = (
            session.query(func.date(LearningSession.started_at))
            .filter(*completed_filter, LearningSession.started_at.is_not(None))
            .distinct()
            .order_by(func.date(LearningSession.started_at))
            .all()
        )
        unique_dates = []
        for (raw_date,) in date_rows:
            if isinstance(raw_date, datetime):
                normalized_date = raw_date.date()
            elif isinstance(raw_date, date):
                normalized_date = raw_date
            else:
                normalized_date = date.fromisoformat(raw_date)
            unique_dates.append(normalized_date)

        consecutive = 1
        max_consecutive = 1 if unique_dates else 0
        for index in range(1, len(unique_dates)):
            current = unique_dates[index]
            previous = unique_dates[index - 1]
            if (current - previous).days == 1:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 1
        stats["consecutive_days"] = max_consecutive

        stats.update(self._get_progress_stats(user_id, session))
        logger.debug(f"User {user_id} stats: {stats}")
        return stats

    def _get_progress_stats(self, user_id: int, session) -> dict[str, Any]:
        """Get voice usage and vocabulary stats from user progress"""
        stats = {}

        progress_rows = (
            session.query(UserProgress.metric_type, UserProgress.metric_value)
            .filter(
                UserProgress.user_id == user_id,
                UserProgress.metric_type.in_(("voice_usage", "vocabulary_size")),
            )
            .order_by(UserProgress.id)
            .all()
        )
        # Preserve the former ``first()`` behavior if an older database has
        # duplicate metric rows: the lowest-id row remains authoritative.
        progress: dict[str, float] = {}
        for metric_type, value in progress_rows:
            progress.setdefault(metric_type, value)
        stats["voice_usage"] = progress.get("voice_usage", 0)
        stats["vocabulary_size"] = int(progress.get("vocabulary_size", 0))

        return stats

    def _check_achievement_criteria(
        self, user_id: int, achievement: dict, stats: dict, session
    ) -> bool:
        """Check if user meets achievement criteria"""
        criteria_type = achievement["criteria_type"]
        criteria_value = achievement["criteria_value"]

        # Check if already earned
        existing = (
            session.query(UserAchievement)
            .join(Achievement)
            .filter(
                UserAchievement.user_id == user_id,
                Achievement.name == achievement["name"],
            )
            .first()
        )

        if existing:
            return False

        # Check criteria
        if criteria_type == "sessions_completed":
            return stats["sessions_completed"] >= criteria_value

        elif criteria_type == "correct_answers":
            return stats["total_correct_answers"] >= criteria_value

        elif criteria_type == "comprehension_score":
            return stats["average_comprehension"] >= criteria_value

        elif criteria_type == "vocabulary_size":
            return stats["vocabulary_size"] >= criteria_value

        elif criteria_type == "topics_completed":
            return stats["topics_completed"] >= criteria_value

        elif criteria_type == "consecutive_days":
            return stats["consecutive_days"] >= criteria_value

        elif criteria_type == "voice_usage":
            return stats["voice_usage"] >= criteria_value

        return False

    def _award_achievement(self, user_id: int, achievement_key: str, session) -> bool:
        """Award an achievement to a user"""
        try:
            achievement_data = self.achievements[achievement_key]

            # Get or create achievement definition
            achievement = (
                session.query(Achievement)
                .filter(Achievement.name == achievement_data["name"])
                .first()
            )

            if not achievement:
                achievement = Achievement(
                    name=achievement_data["name"],
                    description=achievement_data["description"],
                    category=achievement_data["category"],
                    criteria_type=achievement_data["criteria_type"],
                    criteria_value=achievement_data["criteria_value"],
                    points=achievement_data["points"],
                    icon=achievement_data["icon"],
                )
                session.add(achievement)
                session.flush()

            # Create user achievement
            user_achievement = UserAchievement(
                user_id=user_id, achievement_id=achievement.id, earned_at=datetime.now()
            )
            session.add(user_achievement)

            # Persist and publish a notification for the user.
            try:
                title = "Achievement Unlocked"
                message = (
                    f"{achievement_data['name']} (+{achievement_data['points']} pts)"
                )

                db_notification = Notification(
                    user_id=user_id,
                    title=title,
                    message=message,
                    notification_type="achievement",
                    priority="high",
                    is_read=False,
                )
                session.add(db_notification)
                session.flush()
                stage_notification(session, db_notification)
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")

            logger.success(
                f"Awarded achievement '{achievement_data['name']}' to user {user_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to award achievement {achievement_key} to user {user_id}: {e}"
            )
            return False

    def get_user_achievements(
        self, user_id: int, db: Session | None = None
    ) -> list[dict]:
        """Get ALL achievements for a user with progress status"""
        try:
            session_context = nullcontext(db) if db is not None else get_session()
            with session_context as session:
                # Get user stats for progress calculation
                stats = self._get_user_stats(user_id, session)

                # Get all earned achievements
                user_achievements = (
                    session.query(UserAchievement)
                    .options(joinedload(UserAchievement.achievement))
                    .filter(UserAchievement.user_id == user_id)
                    .all()
                )
                earned_achievement_ids = {ua.achievement_id: ua for ua in user_achievements}

                # Get ALL achievements from database
                all_db_achievements = (
                    session.query(Achievement)
                    .filter(Achievement.is_active)
                    .filter(
                        # Show achievements that are either:
                        # 1. System achievements (created_by is None)
                        # 2. Custom achievements targeting this user
                        # 3. Custom achievements with no target (available to all)
                        or_(
                            Achievement.created_by.is_(None),
                            Achievement.target_user_id == user_id,
                            Achievement.target_user_id.is_(None),
                        )
                    )
                    .all()
                )

                achievements = []
                seen_names = set()

                # Process achievements from database
                for ach in all_db_achievements:
                    if ach.name in seen_names:
                        continue
                    seen_names.add(ach.name)

                    # Check if earned
                    ua = earned_achievement_ids.get(ach.id)
                    earned_at = ua.earned_at.isoformat() if ua and ua.earned_at else None

                    # Calculate progress
                    progress = self._calculate_progress(ach, stats) if not earned_at else 100.0

                    achievements.append({
                        "name": ach.name,
                        "description": ach.description or "",
                        "category": ach.category or "general",
                        "points": ach.points or 10,
                        "icon": ach.icon or "🏆",
                        "earned_at": earned_at,
                        "progress": progress,
                    })

                # Also add hardcoded achievements that may not be in DB yet
                for _key, ach_data in self.achievements.items():
                    if ach_data["name"] in seen_names:
                        continue
                    seen_names.add(ach_data["name"])

                    # Check if earned by name
                    earned_at = None
                    for ua in user_achievements:
                        if ua.achievement and ua.achievement.name == ach_data["name"]:
                            earned_at = ua.earned_at.isoformat() if ua.earned_at else None
                            break

                    # Calculate progress
                    progress = self._calculate_progress_from_dict(ach_data, stats) if not earned_at else 100.0

                    achievements.append({
                        "name": ach_data["name"],
                        "description": ach_data["description"],
                        "category": ach_data["category"],
                        "points": ach_data["points"],
                        "icon": ach_data["icon"],
                        "earned_at": earned_at,
                        "progress": progress,
                    })

                return achievements

        except Exception as e:
            logger.exception(f"Failed to get achievements for user {user_id}: {e}")
            return []

    def _calculate_progress(self, achievement: Achievement, stats: dict) -> float:
        """Calculate progress percentage for an achievement"""
        if not achievement.criteria_type or not achievement.criteria_value:
            return 0.0  # Manual achievements have no auto-progress

        return self._calculate_progress_generic(
            achievement.criteria_type,
            achievement.criteria_value,
            stats
        )

    def _calculate_progress_from_dict(self, achievement: dict, stats: dict) -> float:
        """Calculate progress percentage from achievement dict"""
        return self._calculate_progress_generic(
            achievement.get("criteria_type"),
            achievement.get("criteria_value"),
            stats
        )

    def _calculate_progress_generic(self, criteria_type: str, criteria_value: float, stats: dict) -> float:
        """Generic progress calculation based on criteria type"""
        if not criteria_type or not criteria_value:
            return 0.0

        current_value = 0.0

        if criteria_type == "sessions_completed":
            current_value = stats.get("sessions_completed", 0)
        elif criteria_type == "correct_answers":
            current_value = stats.get("total_correct_answers", 0)
        elif criteria_type == "comprehension_score":
            current_value = stats.get("average_comprehension", 0)
        elif criteria_type == "vocabulary_size":
            current_value = stats.get("vocabulary_size", 0)
        elif criteria_type == "topics_completed":
            current_value = stats.get("topics_completed", 0)
        elif criteria_type == "consecutive_days":
            current_value = stats.get("consecutive_days", 0)
        elif criteria_type == "voice_usage":
            current_value = stats.get("voice_usage", 0)

        progress = (current_value / criteria_value) * 100 if criteria_value > 0 else 0
        return min(progress, 100.0)  # Cap at 100%

    def get_categories(self) -> list[str]:
        """Get all predefined achievement categories"""
        categories = set()
        for ach_data in self.achievements.values():
            categories.add(ach_data["category"])
        # Add standard categories
        categories.update(["beginner", "performance", "consistency", "exploration", "vocabulary", "interaction", "custom"])
        return sorted(list(categories))

    def get_user_points(self, user_id: int, db: Session | None = None) -> int:
        """Get total points for a user"""
        try:
            session_context = nullcontext(db) if db is not None else get_session()
            with session_context as session:

                total_points = (
                    session.query(func.sum(Achievement.points))
                    .join(UserAchievement)
                    .filter(UserAchievement.user_id == user_id)
                    .scalar()
                    or 0
                )

                return int(total_points)

        except Exception as e:
            logger.error(f"Failed to get points for user {user_id}: {e}")
            return 0

    def update_progress(
        self, user_id: int, metric_type: str, value: float, db: Session | None = None
    ):
        """Update user progress metric"""
        try:
            if db is not None:
                self._update_progress_in_session(user_id, metric_type, value, db)
                return
            with get_session() as session:
                self._update_progress_in_session(user_id, metric_type, value, session)
        except Exception as exc:
            logger.error(f"Failed to update progress for user {user_id}: {exc}")

    def _update_progress_in_session(
        self, user_id: int, metric_type: str, value: float, session: Session
    ) -> None:
        progress = (
            session.query(UserProgress)
            .filter(
                UserProgress.user_id == user_id,
                UserProgress.metric_type == metric_type,
            )
            .first()
        )

        if progress:
            progress.metric_value = value
            progress.recorded_at = datetime.now()
        else:
            progress = UserProgress(
                user_id=user_id, metric_type=metric_type, metric_value=value
            )
            session.add(progress)

        session.flush()
        logger.debug(f"Updated progress for user {user_id}: {metric_type} = {value}")

    def get_leaderboard(
        self, limit: int = 10, db: Session | None = None
    ) -> list[dict]:
        """Get leaderboard of top users by points"""
        try:
            session_context = nullcontext(db) if db is not None else get_session()
            with session_context as session:
                # Get users with their total points

                leaderboard = (
                    session.query(
                        User.username,
                        User.display_name,
                        func.sum(Achievement.points).label("total_points"),
                        func.count(UserAchievement.id).label("achievement_count"),
                    )
                    .select_from(User)
                    .join(UserAchievement, UserAchievement.user_id == User.id)
                    .join(
                        Achievement,
                        Achievement.id == UserAchievement.achievement_id,
                    )
                    .group_by(User.id, User.username, User.display_name)
                    .order_by(func.sum(Achievement.points).desc())
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "username": row.username,
                        "display_name": row.display_name,
                        "points": int(row.total_points or 0),
                        "achievement_count": row.achievement_count,
                    }
                    for row in leaderboard
                ]

        except Exception as e:
            logger.exception(f"Failed to get leaderboard: {e}")
            return []
