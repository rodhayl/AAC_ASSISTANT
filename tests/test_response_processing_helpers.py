"""Unit tests for the helpers extracted from ``process_response``.

These cover the four private helpers added when the response-processing
pipeline was decomposed: language instruction selection, exact-match
fallback grading, Whisper voice transcription, and history persistence.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, Mock

import pytest
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import LearningSession
from src.aac_app.services.learning import responses as responses_module
from src.aac_app.services.learning.responses import ResponseProcessingMixin


class _Harness(ResponseProcessingMixin):
    """Expose the mixin helpers without the full service constructor."""

    def __init__(self, speech: Mock | None = None):
        self.speech = speech or Mock()


# ---------------------------------------------------------------------------
# _lang_instruction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user_lang", "expected"),
    [
        ("es", "Respond in Spanish."),
        ("es-ES", "Respond in Spanish."),
        ("en", "Respond in English."),
        ("fr", "Respond in English."),
        ("", "Respond in English."),
    ],
)
def test_lang_instruction(user_lang: str, expected: str) -> None:
    assert ResponseProcessingMixin._lang_instruction(user_lang) == expected


# ---------------------------------------------------------------------------
# _exact_match_analysis
# ---------------------------------------------------------------------------


def _last_question() -> dict:
    return {
        "question": "What color is the sky?",
        "choices": ["Green", "Blue", "Red"],
        "correct": 1,
    }


def _translation_service() -> Mock:
    service = Mock()
    service.get.return_value = "Good try!"
    return service


def test_exact_match_analysis_correct_case_insensitive() -> None:
    service = _translation_service()
    service.get.return_value = "Correct!"

    analysis = _Harness()._exact_match_analysis("  blue ", _last_question(), service, "en")

    assert analysis["is_correct"] is True
    assert analysis["confidence"] == 1.0
    assert analysis["encouraging_feedback"] == "Correct!"
    service.get.assert_called_once_with("en", "pages/learning", "correctAnswer")


def test_exact_match_analysis_incorrect_uses_default_miss_confidence() -> None:
    analysis = _Harness()._exact_match_analysis(
        "green", _last_question(), _translation_service(), "en"
    )
    assert analysis["is_correct"] is False
    assert analysis["confidence"] == 0.5  # LLM-failure path


def test_exact_match_analysis_incorrect_honors_custom_miss_confidence() -> None:
    analysis = _Harness()._exact_match_analysis(
        "green",
        _last_question(),
        _translation_service(),
        "en",
        miss_confidence=0.0,  # JSON-parse-failure path
    )
    assert analysis["is_correct"] is False
    assert analysis["confidence"] == 0.0


def test_exact_match_analysis_uses_translation_for_incorrect_feedback() -> None:
    service = _translation_service()
    _Harness()._exact_match_analysis("green", _last_question(), service, "es")
    service.get.assert_called_once_with("es", "pages/learning", "feedback.goodTry")


# ---------------------------------------------------------------------------
# _transcribe_voice_response
# ---------------------------------------------------------------------------


def test_transcribe_voice_success() -> None:
    speech = Mock()
    speech.is_available.return_value = True
    speech.recognize_from_file.return_value = "hola"
    harness = _Harness(speech)

    transcription = harness._transcribe_voice_response(b"audio", None)

    assert transcription == "hola"
    speech.recognize_from_file.assert_called_once()


def test_transcribe_voice_unavailable_speech() -> None:
    speech = Mock()
    speech.is_available.return_value = False
    harness = _Harness(speech)

    with pytest.raises(RuntimeError, match="Voice transcription failed"):
        harness._transcribe_voice_response(b"audio", None)
    speech.recognize_from_file.assert_not_called()


def test_transcribe_voice_empty_transcription_fails_explicitly() -> None:
    speech = Mock()
    speech.is_available.return_value = True
    speech.recognize_from_file.return_value = "   "
    harness = _Harness(speech)

    with pytest.raises(RuntimeError, match="Voice transcription failed"):
        harness._transcribe_voice_response(b"audio", None)


def test_transcribe_voice_exception_fails_explicitly() -> None:
    speech = Mock()
    speech.is_available.return_value = True
    speech.recognize_from_file.side_effect = RuntimeError("whisper crashed")
    harness = _Harness(speech)

    with pytest.raises(RuntimeError, match="Voice transcription failed"):
        harness._transcribe_voice_response(b"audio", None)


def test_transcribe_voice_reuses_audio_path_without_cleanup() -> None:
    speech = Mock()
    speech.is_available.return_value = True
    speech.recognize_from_file.return_value = "hola"
    harness = _Harness(speech)

    transcription = harness._transcribe_voice_response(None, "/tmp/streamed.wav")

    assert transcription == "hola"
    # The streamed request temp file must NOT be removed by the helper.
    speech.recognize_from_file.assert_called_once_with("/tmp/streamed.wav")


def test_transcribe_voice_writes_and_cleans_temporary_file() -> None:
    speech = Mock()
    speech.is_available.return_value = True

    def _fake_recognize(path: str) -> str:
        captured["path"] = path
        return "hola"

    captured: dict[str, str] = {}
    speech.recognize_from_file.side_effect = _fake_recognize
    harness = _Harness(speech)

    transcription = harness._transcribe_voice_response(b"wav-bytes", None)

    assert transcription == "hola"
    temp_path = captured["path"]
    assert temp_path.endswith(".wav")
    assert not os.path.exists(temp_path), "temporary audio file must be cleaned up"


# ---------------------------------------------------------------------------
# _persist_history
# ---------------------------------------------------------------------------


def test_persist_history_commits_and_flags_json_column(
    regular_user, test_db_session: Session
) -> None:
    session = LearningSession(
        user_id=regular_user.id, topic_name="Weather", conversation_history=[]
    )
    test_db_session.add(session)
    test_db_session.flush()

    session.conversation_history = [{"type": "response", "student_answer": "blue"}]

    ResponseProcessingMixin._persist_history(session, test_db_session)

    # The JSON mutation was persisted despite SQLAlchemy's list-change blind spot.
    stored = (
        test_db_session.query(LearningSession)
        .filter(LearningSession.id == session.id)
        .first()
    )
    assert stored.conversation_history == [
        {"type": "response", "student_answer": "blue"}
    ]


# ---------------------------------------------------------------------------
# _build_recent_symbol_context
# ---------------------------------------------------------------------------


def test_recent_symbol_context_extracts_patterns() -> None:
    history = [
        {
            "type": "response",
            "mode": "symbol",
            "symbols": [{"label": "I", "category": "pronouns"}],
        },
        {"type": "feedback", "message": "Great!"},
        {
            "type": "response",
            "mode": "symbol",
            "symbols": [
                {"label": "want", "category": "actions"},
                {"label": "juice", "category": "food"},
            ],
        },
    ]
    context = _Harness()._build_recent_symbol_context(history)
    assert context == "I (pronouns); want + juice (actions/food)"


def test_recent_symbol_context_ignores_non_symbol_entries() -> None:
    history = [
        {"type": "response", "mode": "text", "student_answer": "hi"},
        {"type": "feedback", "message": "Hello!"},
    ]
    assert _Harness()._build_recent_symbol_context(history) == ""


def test_recent_symbol_context_empty_history() -> None:
    assert _Harness()._build_recent_symbol_context([]) == ""
    assert _Harness()._build_recent_symbol_context(None) == ""


# ---------------------------------------------------------------------------
# process_response question-answer branch
# ---------------------------------------------------------------------------


def _question_session(
    test_db_session: Session, user_id: int, question: dict | None = None
) -> LearningSession:
    """Create a session whose history ends with a question entry."""
    default_question = {
        "question": "What color is the sky?",
        "choices": ["Green", "Blue", "Red"],
        "correct": 1,
    }
    session = LearningSession(
        user_id=user_id,
        topic_name="Weather",
        status="active",
        conversation_history=[
            {
                "type": "question",
                "data": question if question is not None else default_question,
            }
        ],
    )
    test_db_session.add(session)
    test_db_session.flush()
    return session


class _FullHarness(ResponseProcessingMixin):
    """Harness with mocks for every collaborator process_response touches."""

    def __init__(
        self,
        llm=None,
        speech=None,
        symbol_semantics=None,
        aac_expander=None,
        aac_prompt_profile=None,
        symbol_analytics=None,
        guardian_profile_service=None,
        provider_type="groq",
    ):
        from src.aac_app.services.aac_expander_service import AACExpanderService
        from src.aac_app.services.learning.common import AACPromptProfile
        from src.aac_app.services.symbol_semantics import SymbolSemantics

        self.llm = llm or Mock()
        self.speech = speech or Mock()
        self.symbol_semantics = symbol_semantics or SymbolSemantics()
        self.aac_expander = aac_expander or AACExpanderService()
        self.aac_prompt_profile = aac_prompt_profile or AACPromptProfile()
        self.symbol_analytics = symbol_analytics or Mock()
        self.guardian_profile_service = guardian_profile_service or Mock()
        self.provider_type = provider_type
        self.default_max_tokens = 256
        self.default_temperature = 0.4

    def _get_system_prompt(self, *args, **kwargs) -> str:
        return "system prompt"

    def _get_user_language(self, *args, **kwargs) -> str:
        return "en"

    def _session_scope(self, db):
        from src.aac_app.db import session_scope

        return session_scope(db)

    def build_conversation_user_prompt(
        self, student_message: str, topic: str, context: str, lang: str
    ) -> str:
        return f"Previous conversation:\n{context}\nStudent: {student_message}\nTopic: {topic}"


@pytest.mark.anyio
async def test_process_response_logs_achievement_update_failure(
    regular_user, test_db_session: Session, monkeypatch, caplog
) -> None:
    session = _question_session(test_db_session, regular_user.id)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value='{"is_correct": true, "confidence": 0.95, "encouraging_feedback": "Great job!"}'
    )

    class FailingAchievementSystem:
        def check_achievements(self, *_args, **_kwargs):
            raise RuntimeError("achievement backend unavailable")

    monkeypatch.setattr(responses_module, "AchievementSystem", FailingAchievementSystem)
    harness = _FullHarness(llm=llm)

    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(str(message)), level="WARNING")
    try:
        result = await harness.process_response(
            session_id=session.id, student_response="blue", db=test_db_session
        )
    finally:
        logger.remove(sink_id)

    assert result["success"] is True
    assert any("Achievement update failed" in message for message in captured)
    assert any("achievement backend unavailable" in message for message in captured)


@pytest.mark.anyio
async def test_process_response_grades_correct_answer_via_llm(
    regular_user, test_db_session: Session
) -> None:
    """A valid question is graded through the LLM and increments stats."""
    session = _question_session(test_db_session, regular_user.id)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value='{"is_correct": true, "confidence": 0.95, "encouraging_feedback": "Great job!"}'
    )
    harness = _FullHarness(llm=llm)

    result = await harness.process_response(
        session_id=session.id, student_response="blue", db=test_db_session
    )

    assert result["success"] is True
    assert result["is_correct"] is True
    assert result["feedback_message"] == "Great job!"
    assert result["provider_used"] == "groq"
    test_db_session.refresh(session)
    assert session.questions_answered == 1
    assert session.correct_answers == 1
    assert session.comprehension_score == 1.0
    assert result["next_action"] == "continue_questions"


@pytest.mark.anyio
async def test_process_response_grades_incorrect_answer(
    regular_user, test_db_session: Session
) -> None:
    session = _question_session(test_db_session, regular_user.id)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value='{"is_correct": false, "confidence": 0.4, "encouraging_feedback": "Almost!"}'
    )
    harness = _FullHarness(llm=llm)

    result = await harness.process_response(
        session_id=session.id, student_response="green", db=test_db_session
    )

    assert result["success"] is True
    assert result["is_correct"] is False
    test_db_session.refresh(session)
    assert session.questions_answered == 1
    assert session.correct_answers == 0


@pytest.mark.anyio
async def test_process_response_accepts_string_boolean(
    regular_user, test_db_session: Session
) -> None:
    """LLM JSON booleans may arrive as strings and are normalized to real bools."""
    session = _question_session(test_db_session, regular_user.id)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=(
            '{"is_correct": "true", "confidence": 0.85, '
            '"encouraging_feedback": "Nice work!"}'
        )
    )
    harness = _FullHarness(llm=llm)

    result = await harness.process_response(
        session_id=session.id, student_response="blue", db=test_db_session
    )

    assert result["success"] is True
    assert result["is_correct"] is True
    assert result["confidence"] == 0.85


@pytest.mark.anyio
async def test_process_response_rejects_invalid_confidence(
    regular_user, test_db_session: Session
) -> None:
    """Confidence outside [0,1] is an explicit failure, never clamped silently."""
    session = _question_session(test_db_session, regular_user.id)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=(
            '{"is_correct": true, "confidence": 3.0, '
            '"encouraging_feedback": "Good"}'
        )
    )
    harness = _FullHarness(llm=llm)

    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(str(message)), level="ERROR")
    try:
        result = await harness.process_response(
            session_id=session.id, student_response="blue", db=test_db_session
        )
    finally:
        logger.remove(sink_id)

    # Stable client message; the precise reason stays in the server log.
    assert result == {"success": False, "error": "Failed to process response"}
    assert any("confidence must be between 0 and 1" in message for message in captured)


@pytest.mark.anyio
async def test_process_response_rejects_incomplete_llm_json(
    regular_user, test_db_session: Session
) -> None:
    """A grading JSON missing the boolean is an explicit failure, not a guess."""
    session = _question_session(test_db_session, regular_user.id)
    llm = Mock()
    llm.generate = AsyncMock(
        return_value='{"confidence": 0.8, "encouraging_feedback": "Good"}'
    )
    harness = _FullHarness(llm=llm)

    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(str(message)), level="ERROR")
    try:
        result = await harness.process_response(
            session_id=session.id, student_response="blue", db=test_db_session
        )
    finally:
        logger.remove(sink_id)

    # Stable client message; the precise reason stays in the server log.
    assert result == {"success": False, "error": "Failed to process response"}
    assert any("incomplete JSON" in message for message in captured)


@pytest.mark.anyio
async def test_process_response_skips_evaluation_for_malformed_question(
    regular_user, test_db_session: Session
) -> None:
    """A malformed persisted question falls back to conversational handling,
    not a deterministic grade."""
    session = _question_session(
        test_db_session, regular_user.id, question={"question": "", "choices": [], "correct": 5}
    )
    llm = Mock()
    llm.generate = AsyncMock(
        return_value='{"response": "Let us talk about the weather!"}'
    )
    harness = _FullHarness(llm=llm)

    result = await harness.process_response(
        session_id=session.id, student_response="hello", db=test_db_session
    )

    assert result["success"] is True
    assert result["feedback_message"] == "Let us talk about the weather!"
    # Conversational responses carry is_correct=None
    assert result["is_correct"] is None


@pytest.mark.anyio
async def test_process_response_missing_session_is_explicit_error(
    test_db_session: Session,
) -> None:
    harness = _FullHarness()
    result = await harness.process_response(
        session_id=999_999, student_response="hello", db=test_db_session
    )
    assert result == {"success": False, "error": "Session not found"}


@pytest.mark.anyio
async def test_process_response_voice_without_audio_is_explicit_error(
    regular_user, test_db_session: Session
) -> None:
    session = _question_session(test_db_session, regular_user.id)
    harness = _FullHarness()

    result = await harness.process_response(
        session_id=session.id,
        student_response="",
        is_voice=True,        db=test_db_session,
    )

    assert result == {"success": False, "error": "No audio data received."}


@pytest.mark.anyio
async def test_process_response_never_echoes_raw_exception(
    regular_user, test_db_session: Session
) -> None:
    """A provider crash returns a stable message; raw internals stay in logs."""
    session = _question_session(test_db_session, regular_user.id)
    llm = Mock()
    llm.generate = AsyncMock(
        side_effect=RuntimeError(
            "provider endpoint http://internal:5432/db leaked a traceback"
        )
    )
    harness = _FullHarness(llm=llm)

    result = await harness.process_response(
        session_id=session.id, student_response="blue", db=test_db_session
    )

    assert result == {"success": False, "error": "Failed to process response"}
    assert "internal" not in result["error"]
