"""Strict LLM-backed question generation."""

import json
import re
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import LearningSession
from ...services.learning.history import append_history_entry


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


def _is_valid_question_data(value: object) -> bool:
    """Validate the small question contract before it reaches persistence."""
    if not isinstance(value, dict):
        return False
    question = value.get("question")
    choices = value.get("choices")
    correct = value.get("correct")
    return (
        isinstance(question, str)
        and bool(question.strip())
        and isinstance(choices, list)
        and len(choices) == 3
        and all(isinstance(choice, str) and bool(choice.strip()) for choice in choices)
        and len({choice.strip().casefold() for choice in choices}) == len(choices)
        and type(correct) is int
        and 0 <= correct < len(choices)
    )


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

                # Generate and validate the question using the configured LLM.
                # Invalid provider output is an explicit failure; never invent
                # a deterministic question in production.
                question_data, response = await self._generate_question_data(
                    session, difficulty, recent_history, db
                )

                # Validate the complete question contract, not only key presence.
                # An out-of-range correct index would be persisted and crash when
                # the student submits an answer.
                if not _is_valid_question_data(question_data):
                    logger.error(f"Invalid question data structure: {question_data}")
                    return {"success": False, "error": "Invalid question format"}

                # Store question in session
                session.conversation_history = append_history_entry(
                    session.conversation_history,
                    {
                        "type": "question",
                        "data": question_data,
                        "difficulty": difficulty,
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
    ) -> tuple[dict | None, str]:
        """Produce adaptive question data from the configured LLM.

        Returns ``(question_data, response)`` where ``response`` is the last
        raw LLM reply. Invalid output or provider failures raise explicitly;
        this method never fabricates a question.
        """
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
    - Never include the correct answer, or an obvious synonym of it, in the question text; the student must recall or produce it
    - Distractors must be plausible, topic-related alternatives of the same kind as the correct answer, not generic filler
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
                temperature=self.default_temperature,
                max_tokens=self.default_max_tokens,
            )

            # Parse JSON response (tolerating markdown fences / prose)
            question_data = extract_json_object(response)
            if question_data is not None and not _is_valid_question_data(question_data):
                question_data = None
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
    Never include the correct answer, or an obvious synonym of it, in the question text.
    Do NOT repeat a question or choice set you already used earlier in this conversation.

    Generate the {difficulty} level question about {session.topic_name} again.
    Reply with only the JSON object:"""

                retry_response = await self.llm.generate(
                    prompt=retry_prompt,
                    system=system_prompt,
                    temperature=min(self.default_temperature, 0.2),
                    max_tokens=self.default_max_tokens,
                )
                retry_data = extract_json_object(retry_response)
                if retry_data is not None and _is_valid_question_data(retry_data):
                    question_data = retry_data
                    response = retry_response
                    logger.info(
                        f"Question JSON recovered after strict-JSON retry "
                        f"(session {session.id})"
                    )
        except Exception as exc:
            raise RuntimeError("LLM question generation failed") from exc

        if question_data is None:
            raise ValueError("LLM returned invalid question JSON after retry")

        return question_data, response
