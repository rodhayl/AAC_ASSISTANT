"""Session lifecycle and persistence operations."""

import contextlib
import re
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import CommunicationBoard, LearningPlan, LearningSession, LearningTask, User
from ...services.achievement_system import AchievementSystem
from .history import append_history_entry

# A display name may carry a machine-generated suffix (e.g. "Admin
# 1787688161578") from older seeding. Reading that 13-digit number aloud adds
# seconds of TTS to the first spoken message for zero value, so strip a
# trailing whitespace-separated numeric token of 4+ digits before greeting.
_TIMESTAMP_SUFFIX_RE = re.compile(r"\s+\d{4,}$")


def _speakable_display_name(display_name: str) -> str:
    """Return a greeting-friendly name without a trailing timestamp suffix."""
    return _TIMESTAMP_SUFFIX_RE.sub("", display_name).strip()


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

                # Layered content safety (Layer 1): never start a session on a
                # topic the student's effective policy blocks, and honor the
                # teacher/admin feature lock on custom topics.
                from ...services.content_safety import (
                    check_text,
                    log_event,
                    resolve_policy_for_user,
                )

                policy = resolve_policy_for_user(user_id, db)
                topic_verdict = check_text(policy, topic)
                blocked_by_lock = policy.feature_blocked("block_custom_topics")
                if blocked_by_lock or topic_verdict.blocked:
                    log_event(
                        user_id=user_id,
                        surface="topic",
                        direction="input",
                        verdict="blocked",
                        matched=list(topic_verdict.matched_terms),
                        detail=(
                            f"feature_lock: block_custom_topics; topic: {topic[:120]}"
                            if blocked_by_lock
                            else topic[:300]
                        ),
                        db=db,
                    )
                    return {
                        "success": False,
                        "error": "Blocked topic",
                        "safety_blocked": True,
                    }

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
                    board_id=board_id,
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

                # Generate the same localized welcome for new and legacy sessions.
                welcome = self._build_welcome_message(user_id, topic, purpose, db, board_id)


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

    def _build_welcome_message(
        self,
        user_id: int,
        topic: str,
        purpose: str | None,
        db: Session,
        board_id: int | None = None,
    ) -> str:
        """Build the localized welcome used for new and legacy sessions."""
        from src.aac_app.services.translation_service import get_translation_service

        user = db.get(User, user_id)
        if not user:
            return ""
        user_lang = self._get_user_language(user_id, db)
        translation_service = get_translation_service()
        topic_labels = {
            "general conversation": "general",
            "daily routines": "daily",
            "food and dining": "food",
            "school and education": "school",
            "emotions and feelings": "emotions",
            "travel and transport": "travel",
            "hobbies and play": "hobbies",
            "health and body": "health",
            "shopping": "shopping",
        }
        topic_key = topic_labels.get(topic.strip().lower(), topic.strip().lower())
        topic_label = translation_service.get(
            user_lang, "pages/learning", f"topics.{topic_key}"
        )
        if topic_label == f"topics.{topic_key}":
            topic_label = topic.strip() or translation_service.get(
                user_lang, "pages/learning", "topics.general"
            )
        board = db.get(CommunicationBoard, board_id) if board_id else None
        board_label = board.name if board else ""
        # Greet with a name that does not force the TTS to read a long
        # machine-generated number aloud (see _speakable_display_name).
        display_name = _speakable_display_name(user.display_name)
        if (purpose or "").lower() == "aac symbols":
            return translation_service.get(
                user_lang, "pages/learning", "welcomeMessageSymbol", name=display_name
            )
        key = "welcomeContext" if board_label else "welcomeMessage"
        return translation_service.get(
            user_lang,
            "pages/learning",
            key,
            name=display_name,
            topic=topic_label,
            board=board_label,
        )

    def get_session_progress(self, session_id: int, db: Session | None = None) -> dict:
        """Get current progress for a learning session"""

        try:
            with self._session_scope(db) as db:
                session = db.get(LearningSession, session_id)
                if not session:
                    return {"success": False, "error": "Session not found"}

                history = session.conversation_history or []
                if history and history[0].get("type") == "question":
                    first_question = history[0].get("data", {}).get("question")
                    if isinstance(first_question, str) and (
                        "Vamos a aprender sobre" in first_question
                        or "Let's learn about" in first_question
                    ):
                        history = [*history]
                        history[0] = {
                            **history[0],
                            "data": {
                                **history[0].get("data", {}),
                                "question": self._build_welcome_message(
                                    session.user_id,
                                    session.topic_name,
                                    session.purpose,
                                    db,
                                    getattr(session, "board_id", None),
                                ),
                            },
                        }

                return {
                    "success": True,
                    "id": session_id,
                    "session_id": session_id,  # Keep for backward compatibility
                    "topic": session.topic_name,
                    "board_id": session.board_id,
                    "status": session.status,
                    "comprehension_score": session.comprehension_score,
                    "questions_asked": session.questions_asked,
                    "questions_answered": session.questions_answered,
                    "correct_answers": session.correct_answers,
                    "started_at": (session.started_at.isoformat() if session.started_at else None),
                    "conversation_history": history,
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
                            "board_id": s.board_id,
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
