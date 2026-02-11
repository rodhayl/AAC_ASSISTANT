import json
import os
import re
import tempfile
from datetime import datetime
from typing import Dict, Union, Optional

from loguru import logger

from ..models.database import (
    LearningPlan,
    LearningSession,
    LearningTask,
    User,
    UserSettings,
    get_session,
)
from ..providers.local_speech_provider import WHISPER_AVAILABLE, LocalSpeechProvider
from ..providers.local_tts_provider import LocalTTSProvider
from ..providers.ollama_provider import OllamaProvider
from ..providers.openrouter_provider import OpenRouterProvider
from ..services.aac_expander_service import AACExpanderService
from ..services.achievement_system import AchievementSystem
from ..services.guardian_profile_service import get_guardian_profile_service
from ..services.symbol_analytics import SymbolAnalytics
from ..services.symbol_semantics import SymbolSemantics
from ..services.translation_service import TranslationService

# AAC-Specific System Prompt for symbol-based communication (fallback if no profile)
AAC_SYSTEM_PROMPT = """You are an AAC-specialized tutor with expertise in Augmentative and Alternative Communication.

Key principles:
1. Students use symbol-based communication which may be telegraphic (missing articles, conjunctions, etc.)
2. Interpret intent from semantic roles (subject, action, object) rather than strict grammar
3. Expand telegraphic phrases into grammatically complete sentences while preserving the student's meaning
4. Use simple, clear language in your responses (max 2-3 sentences)
5. Be encouraging and patient - communication takes effort
6. Ask ONE clarifying question if intent is ambiguous
7. Model proper grammar without correcting the student's AAC usage

Symbol categories guide semantic interpretation:
- Person symbols → subjects/agents (who)
- Action symbols → verbs (what doing)
- Object symbols → targets/themes (what)
- Feeling symbols → emotional states
- Place symbols → locations (where)
- Question symbols → interrogatives

Always celebrate communication attempts and build on the student's message.

When responding:
1. Understand the student's intent deeply
2. Provide a warm, encouraging response
3. Use simple, clear language
4. Ask follow-up questions to keep the conversation flowing"""


def _strip_reasoning(text: str) -> str:
    """
    Lightweight fallback to remove any thinking/reasoning tags from text.

    With JSON mode, this should rarely be needed. It's kept as a safety net
    for when JSON parsing fails or for legacy data.
    """
    if not text:
        return text

    cleaned = text

    # Remove explicit reasoning blocks
    cleaned = re.sub(
        r"```(?:thinking|reasoning)[\s\S]*?```", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)

    # If there's an explicit answer marker, extract that
    for marker in ["final answer:", "final response:", "answer:", "response:"]:
        idx = cleaned.lower().rfind(marker)
        if idx != -1:
            cleaned = cleaned[idx + len(marker) :].strip()
            break

    return cleaned.strip() or text


class AACPromptProfile:
    """
    Optimized prompt configuration specifically for AAC interactions.
    Provides tuned parameters for AAC-specific LLM interactions.

    Note: Response templates have been removed in favor of the
    Guardian Profile template system which provides more flexibility.
    """

    def __init__(self):
        self.max_tokens = 150  # Shorter, focused responses
        self.temperature = 0.6  # Balanced creativity/consistency

    def build_prompt(
        self,
        student_message: str,
        semantic_analysis: Dict,
        expansion_result: Dict,
        topic: str,
        recent_context: str = "",
    ) -> str:
        """
        Build AAC-optimized prompt with semantic and expansion context.

        Args:
            student_message: Original/enriched message from student
            semantic_analysis: Intent and semantic role information
            expansion_result: Grammar expansion result
            topic: Learning session topic
            recent_context: Recent conversation history

        Returns:
            Formatted prompt string for LLM
        """
        intent = semantic_analysis.get("intent", "statement")
        expanded = expansion_result.get("expanded_text", student_message)
        confidence = expansion_result.get("confidence", 0.5)
        transformations = expansion_result.get("transformations", [])

        prompt_parts = []

        # Context from recent conversation
        if recent_context:
            prompt_parts.append(f"Previous conversation:\n{recent_context}\n")

        # Student's communication with expansion details
        prompt_parts.append(f"Student's AAC message: {student_message}")

        if expanded != student_message and confidence > 0.6:
            prompt_parts.append(f"Expanded interpretation: {expanded}")
            if transformations:
                prompt_parts.append(
                    f"Grammar improvements: {', '.join(transformations)}"
                )

        # Semantic intent context
        prompt_parts.append(f"Detected intent: {intent.upper()}")

        # Intent-specific guidance
        intent_guidance = {
            "request": "The student is making a request. Acknowledge what they want and respond supportively.",
            "question": "The student is asking a question. Provide a clear, simple answer.",
            "greeting": "The student is greeting you. Respond warmly and encourage further interaction.",
            "feeling": "The student is expressing an emotion. Show empathy and provide validation.",
            "statement": "The student is making a statement. Acknowledge and build on their message.",
        }

        if intent in intent_guidance:
            prompt_parts.append(intent_guidance[intent])

        # Topic connection
        prompt_parts.append(f"Topic of discussion: {topic}")

        # Response instructions - simple and direct for JSON mode
        prompt_parts.append(
            "\nWrite a friendly, encouraging response to the student (1-2 sentences). "
            "Ask a follow-up question OR share a helpful fact about the topic."
        )

        return "\n".join(prompt_parts)

    def get_params(self) -> Dict:
        """Get optimized LLM parameters for AAC."""
        return {"max_tokens": self.max_tokens, "temperature": self.temperature}


class LearningCompanionService:
    """AI-powered tutoring with local or cloud models"""

    def __init__(
        self,
        llm_provider: Union[OllamaProvider, OpenRouterProvider],
        speech_provider: LocalSpeechProvider,
        tts_provider: LocalTTSProvider,
        default_max_tokens: int = 1024,
        default_temperature: float = 0.5,
    ):
        self.llm = llm_provider
        self.speech = speech_provider
        self.tts = tts_provider

        # LLM behavior defaults (can be overridden via AppSettings)
        self.default_max_tokens = max(64, int(default_max_tokens or 1024))
        # Clamp temperature to reasonable range
        self.default_temperature = float(
            default_temperature if default_temperature is not None else 0.5
        )
        if self.default_temperature < 0.0:
            self.default_temperature = 0.0
        if self.default_temperature > 1.5:
            self.default_temperature = 1.5

        # Determine provider type
        self.provider_type = (
            "openrouter" if isinstance(llm_provider, OpenRouterProvider) else "ollama"
        )

        # Initialize symbol semantics analyzer and expander
        self.symbol_semantics = SymbolSemantics()
        self.aac_expander = AACExpanderService()
        self.aac_prompt_profile = AACPromptProfile()
        self.symbol_analytics = SymbolAnalytics()

        # Guardian profile service for personalized prompts
        self.guardian_profile_service = get_guardian_profile_service()

        logger.info(
            f"Learning Companion Service initialized with {self.provider_type} provider "
            f"(max_tokens={self.default_max_tokens}, temperature={self.default_temperature})"
        )

    def _get_system_prompt(self, user_id: int) -> str:
        """
        Get the personalized system prompt for a user.

        If the user has a guardian profile configured by a teacher/admin,
        use that. Otherwise, fall back to the default AAC system prompt.

        Args:
            user_id: The user's ID

        Returns:
            Personalized system prompt string
        """
        try:
            # Try to get personalized prompt from guardian profile
            prompt = self.guardian_profile_service.build_system_prompt(user_id)
            if prompt and len(prompt) > 50:  # Ensure we got a real prompt
                logger.debug(f"Using personalized prompt for user {user_id}")
                return prompt
        except Exception as e:
            logger.warning(
                f"Failed to get guardian profile prompt for user {user_id}: {e}"
            )

        # Fall back to default prompt
        logger.debug(f"Using default AAC prompt for user {user_id}")
        return AAC_SYSTEM_PROMPT

    def _get_user_language(self, user_id: int) -> str:
        try:
            with get_session() as db:
                settings = (
                    db.query(UserSettings)
                    .filter(UserSettings.user_id == user_id)
                    .first()
                )
                if settings and settings.ui_language:
                    return settings.ui_language
        except Exception:
            pass
        return "es"

    async def start_learning_session(
        self,
        user_id: int,
        topic: str,
        purpose: str = "",
        difficulty: str = "basic",
        board_id: Optional[int] = None,
    ) -> Dict:
        """Start AI tutoring session"""

        logger.info(
            f"Starting learning session for user {user_id}, topic: {topic}, board_id: {board_id}"
        )

        try:
            with get_session() as db:
                # Get user
                user = db.get(User, user_id)
                if not user:
                    return {"success": False, "error": "User not found"}

                # Create learning plan and task
                plan = LearningPlan(
                    user_id=user_id,
                    name=f"Learning: {topic}",
                    description=purpose
                    or f"Interactive learning session about {topic}",
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

                user_lang = self._get_user_language(user_id)
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
                    session.conversation_history.append(
                        {
                            "type": "question",
                            "data": {"question": welcome},
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                db.commit()

                # Achievement: session start
                try:
                    AchievementSystem().check_achievements(user_id)
                except Exception:
                    pass
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

    async def ask_question(self, session_id: int, difficulty: str = None) -> Dict:
        """Generate adaptive question using local LLM"""

        logger.info(f"Generating question for session {session_id}")

        try:
            with get_session() as db:
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
                    session.conversation_history[-3:]
                    if session.conversation_history
                    else []
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
                    system_prompt = self._get_system_prompt(session.user_id)
                    user_lang = self._get_user_language(session.user_id)
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
                    user_lang = self._get_user_language(session.user_id)
                    translation_service = TranslationService()

                    question_text = translation_service.get(
                        user_lang,
                        "pages.learning",
                        "fallbackQuestion.question",
                        {"topic": session.topic_name},
                    )
                    choice1 = translation_service.get(
                        user_lang, "pages.learning", "fallbackQuestion.choice1"
                    )
                    choice2 = translation_service.get(
                        user_lang, "pages.learning", "fallbackQuestion.choice2"
                    )
                    choice3 = translation_service.get(
                        user_lang, "pages.learning", "fallbackQuestion.choice3"
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
                    user_lang = self._get_user_language(session.user_id)
                    translation_service = TranslationService()

                    question_text = translation_service.get(
                        user_lang,
                        "pages.learning",
                        "fallbackQuestion.question",
                        {"topic": session.topic_name},
                    )
                    choice1 = translation_service.get(
                        user_lang, "pages.learning", "fallbackQuestion.choice1"
                    )
                    choice2 = translation_service.get(
                        user_lang, "pages.learning", "fallbackQuestion.choice2"
                    )
                    choice3 = translation_service.get(
                        user_lang, "pages.learning", "fallbackQuestion.choice3"
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

    async def process_response(
        self,
        session_id: int,
        student_response: str,
        is_voice: bool = False,
        audio_data: bytes = None,
        symbols: list = None,
    ) -> Dict:
        """Analyze response and provide feedback"""

        logger.info(f"Processing response for session {session_id}")
        transcription_failed = False
        is_symbol = bool(symbols)

        try:
            with get_session() as db:
                # Get session
                session = db.get(LearningSession, session_id)
                if not session:
                    return {"success": False, "error": "Session not found"}

                # If voice response, transcribe with local Whisper
                if is_voice and audio_data:
                    logger.info("Transcribing voice response")
                    temp_path = None
                    try:
                        if not WHISPER_AVAILABLE or not getattr(
                            self.speech, "model", None
                        ):
                            transcription_failed = True
                            student_response = "[voice message]"
                        else:
                            # Save audio to a temp file for Whisper
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=".wav"
                            ) as tmp:
                                tmp.write(audio_data)
                                temp_path = tmp.name
                            student_response = self.speech.recognize_from_file(
                                temp_path
                            )
                            logger.info(f"Voice transcription: {student_response}")
                            if not student_response or not student_response.strip():
                                transcription_failed = True
                                student_response = "[voice message]"
                    except Exception as transcribe_error:
                        logger.warning(
                            f"Voice transcription failed: {transcribe_error}"
                        )
                        transcription_failed = True
                        student_response = "[voice message]"
                    finally:
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
                elif is_voice and not audio_data:
                    return {"success": False, "error": "No audio data received."}

                # Symbol semantic analysis and expansion
                symbol_analysis = None
                expansion_result = None
                if is_symbol and symbols and len(symbols) > 0:
                    # Analyze semantic intent and roles
                    symbol_analysis = self.symbol_semantics.analyze_sequence(symbols)
                    logger.info(
                        f"Symbol semantic analysis: intent={symbol_analysis.get('intent')}, confidence={symbol_analysis.get('confidence'):.2f}"
                    )

                    # Expand telegraphic AAC into grammatically complete text
                    expansion_result = self.aac_expander.expand(
                        symbols, student_response, symbol_analysis
                    )
                    logger.info(
                        f"AAC expansion: '{student_response}' -> '{expansion_result['expanded_text']}' (transformations: {expansion_result['transformations']})"
                    )

                    # Use expanded text for LLM processing if confidence is high
                    if expansion_result["confidence"] > 0.6:
                        student_response = expansion_result["expanded_text"]

                # Check if there's a question to answer, or just conversational
                last_question = None
                if session.conversation_history:
                    # Look for the most recent question
                    for entry in reversed(session.conversation_history):
                        if entry.get("type") == "question" and "data" in entry:
                            last_question = entry["data"]
                            break

                # Get user language for localization
                user_lang = self._get_user_language(session.user_id)
                translation_service = TranslationService()

                # If transcription failed, return a graceful message without erroring
                if is_voice and transcription_failed:
                    feedback_text = translation_service.get(
                        user_lang, "pages.learning", "errors.transcriptionFailed"
                    )
                    session.conversation_history.append(
                        {
                            "type": "response",
                            "student_answer": student_response,
                            "is_correct": None,
                            "feedback": feedback_text,
                            "confidence": 0.0,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(session, "conversation_history")
                    db.add(session)
                    db.commit()
                    return {
                        "success": True,
                        "is_correct": None,
                        "transcription": (
                            None
                            if student_response == "[voice message]"
                            else student_response
                        ),
                        "feedback_message": feedback_text,
                        "confidence": 0.0,
                        "comprehension_score": session.comprehension_score,
                        "next_action": "continue_questions",
                        "questions_answered": session.questions_answered,
                        "correct_answers": session.correct_answers,
                        "provider_used": self.provider_type,
                    }

                # If there's a specific question, evaluate the answer
                if last_question:
                    # Add language instruction
                    lang_instruction = (
                        "Respond in Spanish."
                        if user_lang.startswith("es")
                        else "Respond in English."
                    )

                    # Analyze response using local LLM
                    analysis_prompt = f"""Question: {last_question['question']}
Student's answer: {student_response}
Correct answer: {last_question['choices'][last_question['correct']]}

Analyze if the student's answer is correct. Consider:
1. Exact matches
2. Semantic similarity
3. Partial understanding

Provide:
1. is_correct (true/false)
2. confidence (0.0-1.0)
3. encouraging_feedback (2 sentences max, be very positive and encouraging)

Format as JSON. {lang_instruction}"""

                    try:
                        # Get personalized system prompt for this user
                        system_prompt = self._get_system_prompt(session.user_id)

                        analysis = await self.llm.generate(
                            prompt=analysis_prompt,
                            system=system_prompt,
                            # Keep grading deterministic and succinct; use a low temperature
                            temperature=0.3,
                            max_tokens=150,
                        )
                    except Exception:
                        is_correct = (
                            student_response.lower().strip()
                            == last_question["choices"][last_question["correct"]]
                            .lower()
                            .strip()
                        )
                        analysis = json.dumps(
                            {
                                "is_correct": is_correct,
                                "confidence": 1.0 if is_correct else 0.5,
                                "encouraging_feedback": translation_service.get(
                                    user_lang, "pages.learning", "feedback.goodTry"
                                ),
                            }
                        )

                    # Parse analysis
                    try:
                        analysis_data = json.loads(analysis.strip())
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse analysis JSON: {analysis}")
                        # Fallback analysis
                        is_correct = (
                            student_response.lower().strip()
                            == last_question["choices"][last_question["correct"]]
                            .lower()
                            .strip()
                        )
                        analysis_data = {
                            "is_correct": is_correct,
                            "confidence": 1.0 if is_correct else 0.0,
                            "encouraging_feedback": translation_service.get(
                                user_lang, "pages.learning", "feedback.goodTry"
                            ),
                        }

                    # Update session stats
                    session.questions_answered += 1
                    if analysis_data.get("is_correct", False):
                        session.correct_answers += 1
                else:
                    # Conversational mode - generate a response
                    logger.info("Processing conversational response")
                    lang_instruction = (
                        "Respond in Spanish."
                        if user_lang.startswith("es")
                        else "Respond in English."
                    )

                    # Build conversation context
                    context = ""
                    if session.conversation_history:
                        recent_messages = session.conversation_history[
                            -5:
                        ]  # Last 5 messages
                        for msg in recent_messages:
                            if msg.get("type") == "response":
                                if msg.get("mode") == "symbol":
                                    context += f"Student (symbols): {msg.get('student_answer', '')}\n"
                                else:
                                    context += (
                                        f"Student: {msg.get('student_answer', '')}\n"
                                    )
                            elif msg.get("type") == "feedback":
                                context += f"Tutor: {msg.get('message', '')}\n"

                    # Make the latest line explicit if it came from AAC symbols
                    student_prompt_line = student_response
                    conversation_prompt = ""
                    aac_params = {}

                    if is_symbol and symbols and symbol_analysis and expansion_result:
                        # Use AAC Prompt Profile for optimized AAC interactions
                        conversation_prompt = self.aac_prompt_profile.build_prompt(
                            student_message=student_response,
                            semantic_analysis=symbol_analysis,
                            expansion_result=expansion_result,
                            topic=session.topic_name,
                            recent_context=context,
                        )
                        aac_params = self.aac_prompt_profile.get_params()
                    elif is_symbol and symbols and symbol_analysis:
                        # Fallback if no expansion result (shouldn't normally happen)
                        expansion_context = (
                            self.symbol_semantics.generate_expansion_context(
                                symbol_analysis, symbols
                            )
                        )
                        context += f"\n{expansion_context}\n"
                        context += "Tutor: The student uses AAC symbols. Interpret their intent and respond with encouragement.\n"

                        # Add recent symbol usage patterns
                        symbol_context = self._build_recent_symbol_context(
                            session.conversation_history
                        )
                        if symbol_context:
                            context += f"Recent symbol patterns: {symbol_context}\n"

                        conversation_prompt = f"""Previous conversation:
{context}

Student's latest message: {student_prompt_line}

Topic: {session.topic_name}

Write a friendly, encouraging response to the student (1-2 sentences). Ask a question or share a fact about {session.topic_name}. {lang_instruction}"""
                    elif is_symbol and symbols:
                        # Fallback if no semantic analysis
                        symbol_list = ", ".join(
                            [
                                f"{s.get('label')} ({s.get('category') or 'symbol'})"
                                for s in symbols
                            ]
                        )
                        student_prompt_line = (
                            f"(AAC symbols) {student_response} [symbols: {symbol_list}]"
                        )
                        context += "Tutor: Note: the student uses AAC symbols; interpret telegraphic phrases and expand into clear, supportive sentences.\n"

                        conversation_prompt = f"""Previous conversation:
{context}

Student's latest message: {student_prompt_line}

Topic: {session.topic_name}

The student uses AAC symbols. Write a supportive response (1-2 friendly sentences). Ask a question or share a fact about {session.topic_name}. {lang_instruction}"""
                    else:
                        # Non-symbol conversational mode
                        conversation_prompt = f"""Previous conversation:
{context}

Student's latest message: {student_prompt_line}

Topic: {session.topic_name}

Write a helpful response to the student (1-2 friendly sentences). Ask a question or share a fact about {session.topic_name}. {lang_instruction}"""

                    try:
                        # Use structured JSON output for clean, parseable responses
                        json_schema = {
                            "type": "object",
                            "properties": {
                                "response": {
                                    "type": "string",
                                    "description": "Your direct response to the student (1-2 friendly sentences)",
                                }
                            },
                            "required": ["response"],
                        }

                        # Use personalized system prompt from guardian profile
                        system_prompt = self._get_system_prompt(session.user_id)
                        user_lang = self._get_user_language(session.user_id)
                        if user_lang.startswith("es"):
                            system_prompt = system_prompt + "\nResponde en español."

                        # Use AAC-optimized parameters if available
                        if aac_params:
                            response_raw = await self.llm.generate(
                                prompt=conversation_prompt,
                                system=system_prompt,
                                temperature=aac_params["temperature"],
                                max_tokens=aac_params["max_tokens"],
                                json_schema=json_schema,
                            )
                        else:
                            response_raw = await self.llm.generate(
                                prompt=conversation_prompt,
                                system=system_prompt,
                                temperature=self.default_temperature,
                                max_tokens=self.default_max_tokens,
                                json_schema=json_schema,
                            )

                        # Parse JSON response
                        try:
                            response_data = json.loads(response_raw)
                            response = response_data.get("response", "").strip()
                        except json.JSONDecodeError:
                            # Fallback if JSON parsing fails - use the raw response
                            logger.warning(
                                "Failed to parse JSON response, using raw text"
                            )
                            response = _strip_reasoning(response_raw.strip())

                    except Exception as e:
                        logger.warning(f"LLM generation error: {e}")
                        response = translation_service.get(
                            user_lang,
                            "pages.learning",
                            "fallbackConversation.goodMessage",
                        )

                    # Validate we have content
                    if not response or len(response.strip()) < 5:
                        response = translation_service.get(
                            user_lang,
                            "pages.learning",
                            "fallbackConversation.interesting",
                        )

                    analysis_data = {
                        "is_correct": None,
                        "confidence": 0.8,
                        "encouraging_feedback": response,
                    }

                # Update comprehension score (running average)
                if session.questions_answered > 0:
                    session.comprehension_score = (
                        session.correct_answers / session.questions_answered
                    )

                # Store response
                entry = {
                    "type": "response",
                    "student_answer": student_response,
                    "is_correct": analysis_data.get("is_correct", False),
                    "feedback": analysis_data.get(
                        "encouraging_feedback",
                        translation_service.get(
                            user_lang, "pages.learning", "feedback.goodTry"
                        ),
                    ),
                    "confidence": analysis_data.get("confidence", 0.5),
                    "timestamp": datetime.now().isoformat(),
                }
                if is_symbol and symbols:
                    entry["mode"] = "symbol"
                    entry["symbols"] = symbols
                    # Store semantic analysis metadata
                    if symbol_analysis:
                        entry["semantic_analysis"] = {
                            "intent": symbol_analysis.get("intent"),
                            "confidence": symbol_analysis.get("confidence"),
                            "semantic_roles": symbol_analysis.get("semantic_roles"),
                            "symbol_count": symbol_analysis.get("symbol_count"),
                            "unique_categories": symbol_analysis.get(
                                "unique_categories"
                            ),
                        }
                    # Store expansion result metadata
                    if expansion_result:
                        entry["expansion"] = {
                            "original": (
                                symbols[0].get("label") if symbols else ""
                            ),  # First symbol
                            "expanded_text": expansion_result["expanded_text"],
                            "confidence": expansion_result["confidence"],
                            "transformations": expansion_result["transformations"],
                        }
                session.conversation_history.append(entry)

                # Mark JSON column as modified (SQLAlchemy doesn't auto-detect list changes)
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(session, "conversation_history")

                db.add(session)
                db.commit()

                # Log symbol usage for analytics (asynchronous, don't fail on error)
                if is_symbol and symbols:
                    try:
                        intent = (
                            symbol_analysis.get("intent") if symbol_analysis else None
                        )
                        self.symbol_analytics.log_symbol_usage(
                            user_id=session.user_id,
                            symbols=symbols,
                            session_id=session.id,
                            semantic_intent=intent,
                            context_topic=session.topic_name,
                            db=db,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to log symbol usage analytics: {e}")

                # Achievement updates
                try:
                    ach = AchievementSystem()
                    # Voice usage increment
                    if is_voice:
                        with get_session() as s:
                            # Read current voice usage then increment via update_progress
                            # For simplicity, increment by 1 event
                            ach.update_progress(
                                session.user_id,
                                "voice_usage",
                                (
                                    ach._get_progress_stats(session.user_id, s).get(
                                        "voice_usage", 0
                                    )
                                    + 1
                                ),
                            )
                    ach.check_achievements(session.user_id)
                except Exception:
                    pass

                # Determine next action
                if (
                    session.comprehension_score >= 0.8
                    and session.questions_answered >= 5
                ):
                    next_action = "ready_for_activity"
                elif (
                    session.comprehension_score < 0.4
                    and session.questions_answered >= 3
                ):
                    next_action = "review_needed"
                else:
                    next_action = "continue_questions"

                logger.info(f"Response processed for session {session_id}")

                return {
                    "success": True,
                    "is_correct": analysis_data.get("is_correct", False),
                    "transcription": student_response if is_voice else None,
                    "feedback_message": analysis_data.get(
                        "encouraging_feedback", "Good job!"
                    ),
                    "confidence": analysis_data.get("confidence", 0.5),
                    "comprehension_score": session.comprehension_score,
                    "next_action": next_action,
                    "questions_answered": session.questions_answered,
                    "correct_answers": session.correct_answers,
                    "provider_used": self.provider_type,
                }

        except Exception as e:
            logger.error(f"Failed to process response: {e}")
            return {"success": False, "error": str(e)}

    def _build_recent_symbol_context(self, conversation_history: list) -> str:
        """Extract recent symbol usage patterns from conversation history."""
        if not conversation_history:
            return ""

        symbol_entries = []
        # Look at last 5 entries for symbol patterns
        for entry in conversation_history[-5:]:
            if entry.get("mode") == "symbol" and entry.get("symbols"):
                symbols = entry["symbols"]
                categories = [s.get("category", "unknown") for s in symbols]
                labels = [s.get("label", "") for s in symbols]
                symbol_entries.append(f"{' + '.join(labels)} ({'/'.join(categories)})")

        if not symbol_entries:
            return ""

        return "; ".join(symbol_entries[-3:])  # Last 3 symbol patterns

    async def end_learning_session(self, session_id: int) -> Dict:
        """End a learning session and provide summary"""

        logger.info(f"Ending learning session {session_id}")

        try:
            with get_session() as db:
                session = db.get(LearningSession, session_id)
                if not session:
                    return {"success": False, "error": "Session not found"}

                # Update session status
                session.status = "completed"
                session.ended_at = datetime.now()

                # Generate summary
                summary_prompt = f"""Create a brief, encouraging summary for a student who completed a learning session about {session.topic_name}.

Session stats:
- Questions answered: {session.questions_answered}
- Correct answers: {session.correct_answers}
- Comprehension score: {session.comprehension_score:.1%}

Be very positive and encouraging. Keep it to 2-3 sentences."""

                # Get personalized system prompt for this user
                system_prompt = self._get_system_prompt(session.user_id)

                summary_raw = await self.llm.generate(
                    prompt=summary_prompt,
                    system=system_prompt,
                    max_tokens=100,
                    temperature=0.7,
                )
                summary = _strip_reasoning(summary_raw)

                db.add(session)
                db.commit()

                # Achievement: session completion
                try:
                    AchievementSystem().check_achievements(session.user_id)
                except Exception:
                    pass
                logger.info(f"Learning session {session_id} ended successfully")

                return {
                    "success": True,
                    "session_id": session_id,
                    "summary": summary,
                    "comprehension_score": session.comprehension_score,
                    "questions_answered": session.questions_answered,
                    "correct_answers": session.correct_answers,
                    "provider_used": self.provider_type,
                }

        except Exception as e:
            logger.error(f"Failed to end learning session: {e}")
            return {"success": False, "error": str(e)}

    def get_session_progress(self, session_id: int) -> Dict:
        """Get current progress for a learning session"""

        try:
            with get_session() as db:
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
                    "started_at": (
                        session.started_at.isoformat() if session.started_at else None
                    ),
                    "conversation_history": session.conversation_history or [],
                }

        except Exception as e:
            logger.error(f"Failed to get session progress: {e}")
            return {"success": False, "error": str(e)}

    def get_user_history(self, user_id: int, limit: int = 10) -> Dict:
        """Get recent learning sessions for a user"""
        try:
            with get_session() as db:
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
                            "created_at": (
                                s.started_at.isoformat() if s.started_at else None
                            ),
                            "completed_at": (
                                s.ended_at.isoformat() if s.ended_at else None
                            ),
                            "questions_answered": s.questions_answered,
                            "correct_answers": s.correct_answers,
                            "comprehension_score": s.comprehension_score,
                        }
                    )

                return {"success": True, "sessions": session_list}

        except Exception as e:
            logger.error(f"Failed to get user history: {e}")
            return {"success": False, "error": str(e)}
