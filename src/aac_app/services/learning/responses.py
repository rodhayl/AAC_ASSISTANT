"""Text, voice, and AAC symbol response processing."""

import contextlib
import json
import os
import tempfile
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from ...models import LearningSession
from ...providers.local_speech_provider import WHISPER_AVAILABLE
from ...services.achievement_system import AchievementSystem
from ...services.translation_service import TranslationService
from .common import _strip_reasoning


class ResponseProcessingMixin:
    async def process_response(
        self,
        session_id: int,
        student_response: str,
        is_voice: bool = False,
        audio_data: bytes = None,
        symbols: list = None,
        db: Session | None = None,
    ) -> dict:
        """Analyze response and provide feedback"""

        logger.info(f"Processing response for session {session_id}")
        transcription_failed = False
        is_symbol = bool(symbols)

        try:
            with self._session_scope(db) as db:
                # Get session
                session = db.get(LearningSession, session_id)
                if not session:
                    return {"success": False, "error": "Session not found"}

                # If voice response, transcribe with local Whisper
                if is_voice and audio_data:
                    logger.info("Transcribing voice response")
                    temp_path = None
                    try:
                        if not WHISPER_AVAILABLE or not getattr(self.speech, "model", None):
                            transcription_failed = True
                            student_response = "[voice message]"
                        else:
                            # Save audio to a temp file for Whisper
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                                tmp.write(audio_data)
                                temp_path = tmp.name
                            student_response = self.speech.recognize_from_file(temp_path)
                            logger.info(f"Voice transcription: {student_response}")
                            if not student_response or not student_response.strip():
                                transcription_failed = True
                                student_response = "[voice message]"
                    except Exception as transcribe_error:
                        logger.warning(f"Voice transcription failed: {transcribe_error}")
                        transcription_failed = True
                        student_response = "[voice message]"
                    finally:
                        if temp_path and os.path.exists(temp_path):
                            with contextlib.suppress(Exception):
                                os.remove(temp_path)
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
                user_lang = self._get_user_language(session.user_id, db)
                translation_service = TranslationService()

                # If transcription failed, return a graceful message without erroring
                if is_voice and transcription_failed:
                    feedback_text = translation_service.get(
                        user_lang, "pages/learning", "errors.transcriptionFailed"
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
                            None if student_response == "[voice message]" else student_response
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
                    analysis_prompt = f"""Question: {last_question["question"]}
    Student's answer: {student_response}
    Correct answer: {last_question["choices"][last_question["correct"]]}

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
                        system_prompt = self._get_system_prompt(session.user_id, db)

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
                            == last_question["choices"][last_question["correct"]].lower().strip()
                        )
                        analysis = json.dumps(
                            {
                                "is_correct": is_correct,
                                "confidence": 1.0 if is_correct else 0.5,
                                "encouraging_feedback": translation_service.get(
                                    user_lang, "pages/learning", "feedback.goodTry"
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
                            == last_question["choices"][last_question["correct"]].lower().strip()
                        )
                        analysis_data = {
                            "is_correct": is_correct,
                            "confidence": 1.0 if is_correct else 0.0,
                            "encouraging_feedback": translation_service.get(
                                user_lang, "pages/learning", "feedback.goodTry"
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
                        recent_messages = session.conversation_history[-5:]  # Last 5 messages
                        for msg in recent_messages:
                            if msg.get("type") == "response":
                                if msg.get("mode") == "symbol":
                                    context += (
                                        f"Student (symbols): {msg.get('student_answer', '')}\n"
                                    )
                                else:
                                    context += f"Student: {msg.get('student_answer', '')}\n"
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
                        expansion_context = self.symbol_semantics.generate_expansion_context(
                            symbol_analysis, symbols
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
                            [f"{s.get('label')} ({s.get('category') or 'symbol'})" for s in symbols]
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
                        system_prompt = self._get_system_prompt(session.user_id, db)
                        user_lang = self._get_user_language(session.user_id, db)
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
                            logger.warning("Failed to parse JSON response, using raw text")
                            response = _strip_reasoning(response_raw.strip())

                    except Exception as e:
                        logger.warning(f"LLM generation error: {e}")
                        response = translation_service.get(
                            user_lang,
                            "pages/learning",
                            "fallbackConversation.goodMessage",
                        )

                    # Validate we have content
                    if not response or len(response.strip()) < 5:
                        response = translation_service.get(
                            user_lang,
                            "pages/learning",
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

                feedback_message = analysis_data.get("encouraging_feedback") or (
                    translation_service.get(user_lang, "pages/learning", "feedback.goodTry")
                )

                # Store response
                entry = {
                    "type": "response",
                    "student_answer": student_response,
                    "is_correct": analysis_data.get("is_correct", False),
                    "feedback": feedback_message,
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
                            "unique_categories": symbol_analysis.get("unique_categories"),
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
                        intent = symbol_analysis.get("intent") if symbol_analysis else None
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
                        current_voice_usage = ach._get_progress_stats(session.user_id, db).get(
                            "voice_usage", 0
                        )
                        ach.update_progress(
                            session.user_id,
                            "voice_usage",
                            current_voice_usage + 1,
                            db=db,
                        )
                    ach.check_achievements(session.user_id, db=db)
                except Exception:
                    pass

                # Determine next action
                if session.comprehension_score >= 0.8 and session.questions_answered >= 5:
                    next_action = "ready_for_activity"
                elif session.comprehension_score < 0.4 and session.questions_answered >= 3:
                    next_action = "review_needed"
                else:
                    next_action = "continue_questions"

                logger.info(f"Response processed for session {session_id}")

                return {
                    "success": True,
                    "is_correct": analysis_data.get("is_correct", False),
                    "transcription": student_response if is_voice else None,
                    "feedback_message": feedback_message,
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

        return "; ".join(symbol_entries[-3:])
