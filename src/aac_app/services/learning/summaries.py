"""Session completion summaries and achievement triggering."""

import contextlib
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import LearningSession
from ...services.achievement_system import AchievementSystem
from ...services.translation_service import TranslationService
from .common import _strip_reasoning


class SessionSummaryMixin:
    async def end_learning_session(self, session_id: int, db: Session | None = None) -> dict:
        """End a learning session and provide summary."""

        logger.info(f"Ending learning session {session_id}")

        try:
            with self._session_scope(db) as db:
                session = db.get(LearningSession, session_id)
                if not session:
                    return {"success": False, "error": "Session not found"}

                session.status = "completed"
                session.ended_at = datetime.now()

                summary_prompt = f"""Create a brief, encouraging summary for a student who completed a learning session about {session.topic_name}.

Session stats:
- Questions answered: {session.questions_answered}
- Correct answers: {session.correct_answers}
- Comprehension score: {session.comprehension_score:.1%}

Be very positive and encouraging. Keep it to 2-3 sentences."""

                system_prompt = self._get_system_prompt(session.user_id, db)

                try:
                    if self.llm is None:
                        raise RuntimeError("LLM provider unavailable")
                    summary_raw = await self.llm.generate(
                        prompt=summary_prompt,
                        system=system_prompt,
                        max_tokens=100,
                        temperature=0.7,
                    )
                    summary = _strip_reasoning(summary_raw)
                except Exception:
                    translation_service = TranslationService()
                    user_lang = self._get_user_language(session.user_id, db)
                    summary = translation_service.get(
                        user_lang,
                        "pages/learning",
                        "fallbackSummary",
                        topic=session.topic_name,
                        questions=session.questions_answered,
                        correct=session.correct_answers,
                    )

                db.add(session)
                db.commit()

                with contextlib.suppress(Exception):
                    AchievementSystem().check_achievements(session.user_id, db=db)
                logger.info(f"Learning session {session_id} ended successfully")

                return {
                    "success": True,
                    "session_id": session_id,
                    "summary": summary,
                    "comprehension_score": session.comprehension_score,
                    "questions_answered": session.questions_answered,
                    "correct_answers": session.correct_answers,
                    "provider_used": self.provider_type,
                    "statistics": {
                        "questions_asked": session.questions_asked,
                        "questions_answered": session.questions_answered,
                        "correct_answers": session.correct_answers,
                        "comprehension_score": session.comprehension_score,
                    },
                }

        except Exception as e:
            logger.error(f"Failed to end learning session: {e}")
            return {"success": False, "error": str(e)}
