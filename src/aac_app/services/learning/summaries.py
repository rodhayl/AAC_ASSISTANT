"""Session completion summaries and achievement triggering."""

import contextlib
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import LearningSession
from ...services.achievement_system import AchievementSystem
from .common import _strip_reasoning


def _safe_summary_fallback(user_lang: str) -> str:
    """Language-appropriate neutral summary when the LLM output stays
    blocked after the constrained retry."""
    if user_lang.startswith("es"):
        return "¡Buen trabajo hoy! Sigue practicando para mejorar cada día."
    return "Great work today! Keep practicing to get better every day."


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

                system_prompt = self._get_system_prompt(
                    session.user_id, db, mode_key=session.mode_key
                )

                if self.llm is None:
                    raise RuntimeError("LLM provider unavailable")
                summary_raw = await self.llm.generate(
                    prompt=summary_prompt,
                    system=system_prompt,
                    max_tokens=100,
                    temperature=0.7,
                )
                summary = _strip_reasoning(summary_raw)
                if not summary.strip():
                    raise ValueError("LLM returned an empty session summary")

                # Layer-1 output gate: never hand a child a summary that trips
                # the deterministic filter. One constrained rewrite is tried;
                # a still-blocked summary falls back to a neutral line.
                from ...services import content_safety as _cs

                s_policy = _cs.resolve_policy_for_user(session.user_id, db)
                s_verdict = _cs.check_text(s_policy, summary)
                if s_verdict.blocked:
                    _cs.log_event(
                        user_id=session.user_id,
                        surface="chat",
                        direction="output",
                        verdict="redirected",
                        matched=list(s_verdict.matched_terms),
                        detail=summary[:300],
                        db=db,
                    )
                    try:
                        retry_raw = await self.llm.generate(
                            prompt=(
                                "The previous session summary was flagged as "
                                "inappropriate for a child. Rewrite it to be "
                                "kind, neutral and age-appropriate in 2-3 "
                                "sentences.\nSummary: " + summary[:500]
                            ),
                            temperature=0.3,
                            max_tokens=100,
                        )
                        retry = _strip_reasoning(retry_raw).strip()
                        if retry and _cs.check_text(s_policy, retry).allowed:
                            summary = retry
                        else:
                            summary = _safe_summary_fallback(self._get_user_language(session.user_id, db))
                    except Exception:
                        summary = _safe_summary_fallback(self._get_user_language(session.user_id, db))

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
