"""Session lifecycle and persistence operations."""

import contextlib
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import LearningPlan, LearningSession, LearningTask, User
from ...services.achievement_system import AchievementSystem
from .history import append_history_entry


class SessionLifecycleMixin:
    def start_learning_session(
        self,
        user_id: int,
        topic: str,
        purpose: str = "",
        difficulty: str = "basic",
        board_id: int | None = None,
        mode_key: str | None = None,
        db: Session | None = None,
    ) -> dict:
        """Start AI tutoring session"""

        logger.info(
            f"Starting learning session for user {user_id}, topic: {topic}, board_id: {board_id}"
        )

        try:
            with self._session_scope(db) as db:
                # Get user
                user = db.get(User, user_id)
                if not user:
                    return {"success": False, "error": "User not found"}

                # Create learning plan and task
                plan = LearningPlan(
                    user_id=user_id,
                    name=f"Learning: {topic}",
                    description=purpose or f"Interactive learning session about {topic}",
                    difficulty=difficulty,
                )
                db.add(plan)
                db.flush()  # Get plan ID

                task = LearningTask(
                    plan_id=plan.id,
                    name=f"Explore {topic}",
                    description=f"Learn about {topic} through interactive questions",
                    task_type="learning_companion",
                    status="in_progress",
                )
                db.add(task)
                db.flush()  # Get task ID

                # Create session record
                session = LearningSession(
                    user_id=user_id,
                    topic_name=topic,
                    purpose=purpose,
                    mode_key=mode_key,
                    status="active",
                    conversation_history=[],
                    comprehension_score=0.0,
                    started_at=datetime.now(),
                )
                db.add(session)
                db.flush()  # Get session ID

                session_id = session.id
                plan_id = plan.id
                task_id = task.id

                # Generate welcome message with local LLM
                welcome = ""

                # Use existing translation system
                from src.aac_app.services.translation_service import (
                    get_translation_service,
                )

                user_lang = self._get_user_language(user_id, db)
                logger.debug(f"user_lang resolved to: {user_lang}")
                ts = get_translation_service()

                # Check if it's a symbol-first session
                if purpose and purpose.lower() == "aac symbols":
                    # For Symbol First, we want a minimal greeting or instruction
                    # Currently using welcomeMessageShort if available, or just a simple "Hi"
                    # But user said: "Just hardcode a welcome message instead of sending a message to the LLM to say just 'hi'"
                    # And "make sure this message is translated"

                    # We will use a specific key for symbol-first greeting
                    welcome = ts.get(
                        user_lang,
                        "pages/learning",
                        "welcomeMessageSymbol",  # New key we should add
                        name=user.display_name,
                    )

                    # Fallback if key doesn't exist yet (safeguard)
                    if not welcome or welcome == "welcomeMessageSymbol":
                        welcome = ts.get(
                            user_lang,
                            "pages/learning",
                            "welcomeMessage",
                            name=user.display_name,
                            topic=topic,
                        )
                else:
                    # Standard welcome message
                    welcome = ts.get(
                        user_lang,
                        "pages/learning",
                        "welcomeMessage",
                        name=user.display_name,
                        topic=topic,
                    )

                # Add welcome message to conversation history if it exists
                if welcome:
                    session.conversation_history = append_history_entry(
                        session.conversation_history,
                        {
                            "type": "question",
                            "data": {"question": welcome},
                            "timestamp": datetime.now().isoformat(),
                        },
                    )

                db.commit()

                # Achievement: session start
                with contextlib.suppress(Exception):
                    AchievementSystem().check_achievements(user_id, db=db)
                logger.info(f"Learning session {session_id} started successfully")

                return {
                    "success": True,
                    "session_id": session_id,
                    "plan_id": plan_id,
                    "task_id": task_id,
                    "board_id": board_id,
                    "welcome_message": welcome,
                    "topic": topic,
                    "difficulty": difficulty,
                    "provider_used": self.provider_type,
                }

        except Exception as e:
            logger.error(f"Failed to start learning session: {e}")
            return {"success": False, "error": str(e)}

    def get_session_progress(self, session_id: int, db: Session | None = None) -> dict:
        """Get current progress for a learning session"""

        try:
            with self._session_scope(db) as db:
                session = db.get(LearningSession, session_id)
                if not session:
                    return {"success": False, "error": "Session not found"}

                return {
                    "success": True,
                    "id": session_id,
                    "session_id": session_id,  # Keep for backward compatibility
                    "topic": session.topic_name,
                    "status": session.status,
                    "comprehension_score": session.comprehension_score,
                    "questions_asked": session.questions_asked,
                    "questions_answered": session.questions_answered,
                    "correct_answers": session.correct_answers,
                    "started_at": (session.started_at.isoformat() if session.started_at else None),
                    "conversation_history": session.conversation_history or [],
                }

        except Exception as e:
            logger.error(f"Failed to get session progress: {e}")
            return {"success": False, "error": str(e)}

    def get_user_history(self, user_id: int, limit: int = 10, db: Session | None = None) -> dict:
        """Get recent learning sessions for a user"""
        try:
            with self._session_scope(db) as db:
                sessions = (
                    db.query(LearningSession)
                    .filter(LearningSession.user_id == user_id)
                    .order_by(LearningSession.started_at.desc())
                    .limit(limit)
                    .all()
                )

                session_list = []
                for s in sessions:
                    session_list.append(
                        {
                            "id": s.id,
                            "topic": s.topic_name,
                            "purpose": s.purpose or "practice",
                            "status": s.status,
                            "created_at": (s.started_at.isoformat() if s.started_at else None),
                            "completed_at": (s.ended_at.isoformat() if s.ended_at else None),
                            "questions_answered": s.questions_answered,
                            "correct_answers": s.correct_answers,
                            "comprehension_score": s.comprehension_score,
                        }
                    )

                return {"success": True, "sessions": session_list}

        except Exception as e:
            logger.error(f"Failed to get user history: {e}")
            return {"success": False, "error": str(e)}
