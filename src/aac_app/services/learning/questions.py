"""Question generation and deterministic fallback questions."""

import json
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import LearningSession
from ...services.translation_service import TranslationService


class QuestionGenerationMixin:
    async def ask_question(
        self, session_id: int, difficulty: str = None, db: Session | None = None
    ) -> dict:
        """Generate adaptive question using local LLM"""

        logger.info(f"Generating question for session {session_id}")

        try:
            with self._session_scope(db) as db:
                # Get session
                session = db.get(LearningSession, session_id)
                if not session:
                    return {"success": False, "error": "Session not found"}

                # Adjust difficulty based on comprehension
                if difficulty is None:
                    if session.comprehension_score < 0.4:
                        difficulty = "basic"
                    elif session.comprehension_score < 0.7:
                        difficulty = "intermediate"
                    else:
                        difficulty = "advanced"

                # Get conversation history (last 3 exchanges)
                recent_history = (
                    session.conversation_history[-3:] if session.conversation_history else []
                )

                # Generate question using local Ollama
                prompt = f"""Generate a {difficulty} level question about {session.topic_name}.

    Previous conversation: {json.dumps(recent_history)}

    Requirements:
    - Appropriate for AAC users with communication difficulties
    - Clear and simple language
    - Include 3-4 answer choices
    - Make it engaging and encouraging
    - Format as JSON: {{"question": "...", "choices": ["A", "B", "C"], "correct": 0}}
    """

                try:
                    # Get personalized system prompt for this user
                    system_prompt = self._get_system_prompt(session.user_id, db)
                    user_lang = self._get_user_language(session.user_id, db)
                    if user_lang.startswith("es"):
                        system_prompt = system_prompt + "\nResponde en español."

                    response = await self.llm.generate(
                        prompt=prompt,
                        system=system_prompt,
                        temperature=0.8,
                        max_tokens=200,
                    )
                except Exception:
                    # Fallback to translated question
                    user_lang = self._get_user_language(session.user_id, db)
                    translation_service = TranslationService()

                    question_text = translation_service.get(
                        user_lang,
                        "pages/learning",
                        "fallbackQuestion.question",
                        topic=session.topic_name,
                    )
                    choice1 = translation_service.get(
                        user_lang, "pages/learning", "fallbackQuestion.choice1"
                    )
                    choice2 = translation_service.get(
                        user_lang, "pages/learning", "fallbackQuestion.choice2"
                    )
                    choice3 = translation_service.get(
                        user_lang, "pages/learning", "fallbackQuestion.choice3"
                    )

                    response = json.dumps(
                        {
                            "question": question_text,
                            "choices": [choice1, choice2, choice3],
                            "correct": 0,
                        }
                    )

                # Parse JSON response
                try:
                    question_data = json.loads(response.strip())
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse question JSON: {response}")
                    # Fallback to translated question
                    user_lang = self._get_user_language(session.user_id, db)
                    translation_service = TranslationService()

                    question_text = translation_service.get(
                        user_lang,
                        "pages/learning",
                        "fallbackQuestion.question",
                        topic=session.topic_name,
                    )
                    choice1 = translation_service.get(
                        user_lang, "pages/learning", "fallbackQuestion.choice1"
                    )
                    choice2 = translation_service.get(
                        user_lang, "pages/learning", "fallbackQuestion.choice2"
                    )
                    choice3 = translation_service.get(
                        user_lang, "pages/learning", "fallbackQuestion.choice3"
                    )

                    question_data = {
                        "question": question_text,
                        "choices": [choice1, choice2, choice3],
                        "correct": 0,
                    }

                # Validate question data
                required_fields = ["question", "choices", "correct"]
                if not all(field in question_data for field in required_fields):
                    logger.error(f"Invalid question data structure: {question_data}")
                    return {"success": False, "error": "Invalid question format"}

                # Store question in session
                session.conversation_history.append(
                    {
                        "type": "question",
                        "data": question_data,
                        "difficulty": difficulty,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                session.questions_asked += 1

                # Mark JSON column as modified (SQLAlchemy doesn't auto-detect list changes)
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(session, "conversation_history")

                db.add(session)
                db.commit()

                logger.info(f"Question generated for session {session_id}")

                return {
                    "success": True,
                    "question_id": len(session.conversation_history) - 1,
                    "question_text": question_data["question"],
                    "choices": question_data["choices"],
                    "difficulty": difficulty,
                    "correct_answer_index": question_data["correct"],
                    "provider_used": self.provider_type,
                }

        except Exception as e:
            logger.error(f"Failed to generate question: {e}")
            return {"success": False, "error": str(e)}
