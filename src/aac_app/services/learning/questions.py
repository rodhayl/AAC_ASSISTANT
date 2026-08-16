"""Question generation and deterministic fallback questions."""

import json
import re
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import LearningSession
from ...services.learning.history import append_history_entry
from ...services.translation_service import TranslationService


def extract_json_object(text: str | None) -> dict | None:
    """Parse a JSON object from an LLM response.

    Tolerates markdown code fences (e.g. ```json ... ```) and surrounding
    prose, which smaller local models sometimes add even when told not to.
    Returns ``None`` when no parseable JSON object can be found.
    """
    if not text:
        return None

    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Last resort: scan for the first balanced {...} block that parses,
    # skipping over any earlier brace groups (e.g. incidental prose braces).
    search_from = 0
    while True:
        start = text.find("{", search_from)
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        block_end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    block_end = i
                    break
        if block_end == -1:
            return None
        try:
            parsed = json.loads(text[start : block_end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        search_from = block_end + 1


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

                required_fields = ("question", "choices", "correct")

                # Generate the question (LLM with a strict-JSON retry, then a
                # translated fallback) and validate its shape.
                question_data, response, is_fallback = await self._generate_question_data(
                    session, difficulty, recent_history, db
                )

                # Validate question data
                if not all(field in question_data for field in required_fields):
                    logger.error(f"Invalid question data structure: {question_data}")
                    return {"success": False, "error": "Invalid question format"}

                # Store question in session
                session.conversation_history = append_history_entry(
                    session.conversation_history,
                    {
                        "type": "question",
                        "data": question_data,
                        "difficulty": difficulty,
                        "source": "fallback" if is_fallback else "llm",
                        "timestamp": datetime.now().isoformat(),
                    },
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
                    "source": "fallback" if is_fallback else "llm",
                }

        except Exception as e:
            logger.error(f"Failed to generate question: {e}")
            return {"success": False, "error": str(e)}

    async def _generate_question_data(
        self,
        session: LearningSession,
        difficulty: str,
        recent_history: list,
        db: Session | None,
    ) -> tuple[dict | None, str, bool]:
        """Produce adaptive question data: LLM, strict-JSON retry, fallback.

        Returns ``(question_data, response, is_fallback)`` where ``response``
        is the last raw LLM reply (empty when generation never reached the
        model) and ``is_fallback`` is True only when the deterministic
        translated template was used. ``question_data`` is ``None`` only when
        generation itself raised before assigning a value.
        """
        required_fields = ("question", "choices", "correct")
        response = ""
        try:
            prompt = f"""Generate a {difficulty} level question about {session.topic_name}.

    Previous conversation: {json.dumps(recent_history)}

    Requirements:
    - Appropriate for AAC users with communication difficulties
    - Clear and simple language
    - Include exactly 3 answer choices
    - Make it engaging and encouraging
    - The "correct" field is the 0-based index of the right answer in "choices"
    - Do NOT repeat a question or choice set you already used earlier in this conversation

    RESPOND ONLY WITH VALID JSON. No greetings, no explanations, no markdown.
    Use exactly this format (shown for a different topic):
    {{"question": "Which animal says 'miau'?", "choices": ["Cat", "Dog", "Cow"], "correct": 0}}

    Now output the JSON question about {session.topic_name}:"""

            # Get personalized system prompt for this user
            system_prompt = self._get_system_prompt(
                session.user_id, db, mode_key=session.mode_key
            )
            user_lang = self._get_user_language(session.user_id, db)
            if user_lang.startswith("es"):
                system_prompt = system_prompt + "\nResponde en español."

            response = await self.llm.generate(
                prompt=prompt,
                system=system_prompt,
                temperature=0.8,
                max_tokens=200,
            )

            # Parse JSON response (tolerating markdown fences / prose)
            question_data = extract_json_object(response)
            if question_data is None:
                # Corrective retry: the model ignored the JSON contract.
                logger.warning(
                    f"Question JSON parse failed (session {session.id}); "
                    "retrying with strict-JSON prompt"
                )
                retry_prompt = f"""Your previous reply was not valid JSON:

    {response}

    You must reply only with valid JSON. Do not add any text, greetings,
    explanations, or markdown before or after the JSON object.
    Format: {{"question": "...", "choices": ["A", "B", "C"], "correct": 0}}
    Do NOT repeat a question or choice set you already used earlier in this conversation.

    Generate the {difficulty} level question about {session.topic_name} again.
    Reply with only the JSON object:"""

                retry_response = await self.llm.generate(
                    prompt=retry_prompt,
                    system=system_prompt,
                    temperature=0.2,
                    max_tokens=200,
                )
                retry_data = extract_json_object(retry_response)
                if retry_data is not None and all(
                    field in retry_data for field in required_fields
                ):
                    question_data = retry_data
                    response = retry_response
                    logger.info(
                        f"Question JSON recovered after strict-JSON retry "
                        f"(session {session.id})"
                    )
        except Exception:
            question_data = None

        is_fallback = question_data is None
        if question_data is None:
            if response:
                logger.error(f"Failed to parse question JSON: {response}")
            else:
                logger.error(
                    "LLM question generation failed; using fallback question"
                )
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

        return question_data, response, is_fallback
