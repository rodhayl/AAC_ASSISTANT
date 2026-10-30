from datetime import datetime
from typing import Any, Dict, List

from loguru import logger

from ..models.database import (
    Achievement,
    LearningSession,
    Notification,
    User,
    UserAchievement,
    UserProgress,
    get_session,
)
from .notification_service import (
    NotificationPriority,
    NotificationType,
    get_notification_service,
)


class AchievementSystem:
    """Gamification and achievement system for AAC learning"""

    def __init__(self):
        self.achievements = self._initialize_achievements()
        logger.info("Achievement system initialized")

    def _initialize_achievements(self) -> Dict[str, Dict]:
        """Initialize predefined achievements"""
        return {
            **self._get_beginner_achievements(),
            **self._get_performance_achievements(),
            **self._get_consistency_achievements(),
            **self._get_exploration_achievements(),
        }

    def _get_beginner_achievements(self) -> Dict[str, Dict]:
        """Get beginner category achievements"""
        return {
            "first_steps": {
                "name": "First Steps",
                "description": "Complete your first learning session",
                "category": "beginner",
                "criteria_type": "sessions_completed",
                "criteria_value": 1,
                "points": 10,
                "icon": "🎯",
            },
            "vocabulary_explorer": {
                "name": "Vocabulary Explorer",
                "description": "Learn 10 new words",
                "category": "vocabulary",
                "criteria_type": "vocabulary_size",
                "criteria_value": 10,
                "points": 25,
                "icon": "📚",
            },
        }

    def _get_performance_achievements(self) -> Dict[str, Dict]:
        """Get performance category achievements"""
        return {
            "quick_learner": {
                "name": "Quick Learner",
                "description": "Answer 5 questions correctly",
                "category": "performance",
                "criteria_type": "correct_answers",
                "criteria_value": 5,
                "points": 20,
                "icon": "⚡",
            },
            "comprehension_champion": {
                "name": "Comprehension Champion",
                "description": "Achieve 80% comprehension score",
                "category": "performance",
                "criteria_type": "comprehension_score",
                "criteria_value": 0.8,
                "points": 100,
                "icon": "🏆",
            },
        }

    def _get_consistency_achievements(self) -> Dict[str, Dict]:
        """Get consistency category achievements"""
        return {
            "streak_master": {
                "name": "Streak Master",
                "description": "Complete sessions for 3 consecutive days",
                "category": "consistency",
                "criteria_type": "consecutive_days",
                "criteria_value": 3,
                "points": 50,
                "icon": "🔥",
            },
            "dedicated_learner": {
                "name": "Dedicated Learner",
                "description": "Complete 10 learning sessions",
                "category": "consistency",
                "criteria_type": "sessions_completed",
                "criteria_value": 10,
                "points": 75,
                "icon": "📖",
            },
        }

    def _get_exploration_achievements(self) -> Dict[str, Dict]:
        """Get exploration and interaction achievements"""
        return {
            "topic_expert": {
                "name": "Topic Expert",
                "description": "Complete sessions in 5 different topics",
                "category": "exploration",
                "criteria_type": "topics_completed",
                "criteria_value": 5,
                "points": 60,
                "icon": "🌟",
            },
            "voice_pioneer": {
                "name": "Voice Pioneer",
                "description": "Use voice input 10 times",
                "category": "interaction",
                "criteria_type": "voice_usage",
                "criteria_value": 10,
                "points": 30,
                "icon": "🎤",
            },
        }

    def check_achievements(self, user_id: int) -> List[Dict]:
        """Check and award achievements for a user"""
        logger.info(f"Checking achievements for user {user_id}")

        newly_earned = []

        try:
            with get_session() as session:
                user = session.get(User, user_id)
                if not user:
                    logger.error(f"User {user_id} not found")
                    return []

                # Get user's current stats
                stats = self._get_user_stats(user_id, session)

                # Check each achievement
                for achievement_key, achievement_data in self.achievements.items():
                    if self._check_achievement_criteria(
                        user_id, achievement_data, stats, session
                    ):
                        # Award achievement
                        earned = self._award_achievement(
                            user_id, achievement_key, session
                        )
                        if earned:
                            newly_earned.append(achievement_data)

                session.commit()

                if newly_earned:
                    logger.success(
                        f"Awarded {len(newly_earned)} new achievements to user {user_id}"
                    )

                return newly_earned

        except Exception as e:
            logger.error(f"Failed to check achievements for user {user_id}: {e}")
            return []

    def _get_user_stats(self, user_id: int, session) -> Dict[str, Any]:
        """Get comprehensive user statistics"""
        stats = {}

        # Get all completed sessions
        sessions = (
            session.query(LearningSession)
            .filter(
                LearningSession.user_id == user_id,
                LearningSession.status == "completed",
            )
            .all()
        )

        # Gather statistics from different sources
        stats.update(self._get_session_stats(sessions))
        stats.update(self._get_topic_stats(sessions))
        stats.update(self._get_streak_stats(sessions))
        stats.update(self._get_progress_stats(user_id, session))

        logger.debug(f"User {user_id} stats: {stats}")
        return stats

    def _get_session_stats(self, sessions) -> Dict[str, Any]:
        """Calculate statistics from learning sessions"""
        stats = {}
        stats["sessions_completed"] = len(sessions)
        stats["total_questions_answered"] = sum(s.questions_answered for s in sessions)
        stats["total_correct_answers"] = sum(s.correct_answers for s in sessions)

        # Comprehension score (average of all sessions)
        if sessions:
            comprehension_scores = [
                s.comprehension_score for s in sessions if s.comprehension_score > 0
            ]
            stats["average_comprehension"] = (
                sum(comprehension_scores) / len(comprehension_scores)
                if comprehension_scores
                else 0
            )
        else:
            stats["average_comprehension"] = 0

        return stats

    def _get_topic_stats(self, sessions) -> Dict[str, Any]:
        """Calculate topic-related statistics"""
        topics = set(s.topic_name for s in sessions)
        return {"topics_completed": len(topics)}

    def _get_streak_stats(self, sessions) -> Dict[str, Any]:
        """Calculate consecutive days streak"""
        if not sessions:
            return {"consecutive_days": 0}

        session_dates = [s.started_at.date() for s in sessions]
        unique_dates = sorted(set(session_dates))

        consecutive = 1
        max_consecutive = 1
        for i in range(1, len(unique_dates)):
            if (unique_dates[i] - unique_dates[i - 1]).days == 1:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 1

        return {"consecutive_days": max_consecutive}

    def _get_progress_stats(self, user_id: int, session) -> Dict[str, Any]:
        """Get voice usage and vocabulary stats from user progress"""
        stats = {}

        # Voice usage
        voice_progress = (
            session.query(UserProgress)
            .filter(
                UserProgress.user_id == user_id,
                UserProgress.metric_type == "voice_usage",
            )
            .first()
        )
        stats["voice_usage"] = voice_progress.metric_value if voice_progress else 0

        # Vocabulary size
        vocab_progress = (
            session.query(UserProgress)
            .filter(
                UserProgress.user_id == user_id,
                UserProgress.metric_type == "vocabulary_size",
            )
            .first()
        )
        stats["vocabulary_size"] = (
            int(vocab_progress.metric_value) if vocab_progress else 0
        )

        return stats

    def _check_achievement_criteria(
        self, user_id: int, achievement: Dict, stats: Dict, session
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

            # Send real-time SSE notification and persist to database
            try:
                title = "Achievement Unlocked"
                message = (
                    f"{achievement_data['name']} (+{achievement_data['points']} pts)"
                )

                # Real-time SSE notification
                svc = get_notification_service()
                svc.show_notification(
                    title=title,
                    message=message,
                    config={
                        "notification_type": NotificationType.ACHIEVEMENT,
                        "priority": NotificationPriority.HIGH,
                        "show_desktop": False,
                    },
                )

                # Persist notification to database
                db_notification = Notification(
                    user_id=user_id,
                    title=title,
                    message=message,
                    notification_type="achievement",
                    priority="high",
                    is_read=False,
                )
                session.add(db_notification)
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

    def get_user_achievements(self, user_id: int) -> List[Dict]:
        """Get ALL achievements for a user with progress status"""
        try:
            with get_session() as session:
                # Get user stats for progress calculation
                stats = self._get_user_stats(user_id, session)

                # Get all earned achievements
                user_achievements = (
                    session.query(UserAchievement)
                    .filter(UserAchievement.user_id == user_id)
                    .all()
                )
                earned_achievement_ids = {ua.achievement_id: ua for ua in user_achievements}

                # Get ALL achievements from database
                all_db_achievements = (
                    session.query(Achievement)
                    .filter(Achievement.is_active == True)
                    .filter(
                        # Show achievements that are either:
                        # 1. System achievements (created_by is None)
                        # 2. Custom achievements targeting this user
                        # 3. Custom achievements with no target (available to all)
                        (Achievement.created_by == None) |
                        (Achievement.target_user_id == user_id) |
                        (Achievement.target_user_id == None)
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
                for key, ach_data in self.achievements.items():
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
            logger.error(f"Failed to get achievements for user {user_id}: {e}")
            return []

    def _calculate_progress(self, achievement: Achievement, stats: Dict) -> float:
        """Calculate progress percentage for an achievement"""
        if not achievement.criteria_type or not achievement.criteria_value:
            return 0.0  # Manual achievements have no auto-progress

        return self._calculate_progress_generic(
            achievement.criteria_type,
            achievement.criteria_value,
            stats
        )

    def _calculate_progress_from_dict(self, achievement: Dict, stats: Dict) -> float:
        """Calculate progress percentage from achievement dict"""
        return self._calculate_progress_generic(
            achievement.get("criteria_type"),
            achievement.get("criteria_value"),
            stats
        )

    def _calculate_progress_generic(self, criteria_type: str, criteria_value: float, stats: Dict) -> float:
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

    def get_categories(self) -> List[str]:
        """Get all predefined achievement categories"""
        categories = set()
        for ach_data in self.achievements.values():
            categories.add(ach_data["category"])
        # Add standard categories
        categories.update(["beginner", "performance", "consistency", "exploration", "vocabulary", "interaction", "custom"])
        return sorted(list(categories))

    def get_user_points(self, user_id: int) -> int:
        """Get total points for a user"""
        try:
            with get_session() as session:
                from sqlalchemy import func

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

    def update_progress(self, user_id: int, metric_type: str, value: float):
        """Update user progress metric"""
        try:
            with get_session() as session:
                # Create or update progress record
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

                session.commit()
                logger.debug(
                    f"Updated progress for user {user_id}: {metric_type} = {value}"
                )

        except Exception as e:
            logger.error(f"Failed to update progress for user {user_id}: {e}")

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get leaderboard of top users by points"""
        try:
            with get_session() as session:
                # Get users with their total points
                from sqlalchemy import func

                leaderboard = (
                    session.query(
                        User.username,
                        User.display_name,
                        func.sum(Achievement.points).label("total_points"),
                        func.count(UserAchievement.id).label("achievement_count"),
                    )
                    .join(UserAchievement)
                    .join(Achievement)
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
            logger.error(f"Failed to get leaderboard: {e}")
            return []
