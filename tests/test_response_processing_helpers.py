"""Unit tests for the helpers extracted from ``process_response``.

These cover the four private helpers added when the response-processing
pipeline was decomposed: language instruction selection, exact-match
fallback grading, Whisper voice transcription, and history persistence.
"""

from __future__ import annotations

import os
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from src.aac_app.models import LearningSession
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
    analysis = _Harness()._exact_match_analysis(
        "  blue ", _last_question(), _translation_service(), "en"
    )
    assert analysis["is_correct"] is True
    assert analysis["confidence"] == 1.0
    assert analysis["encouraging_feedback"] == "Good try!"


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


def test_exact_match_analysis_uses_translation_for_feedback() -> None:
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

    transcription, failed = harness._transcribe_voice_response(b"audio", None)

    assert transcription == "hola"
    assert failed is False
    speech.recognize_from_file.assert_called_once()


def test_transcribe_voice_unavailable_speech() -> None:
    speech = Mock()
    speech.is_available.return_value = False
    harness = _Harness(speech)

    transcription, failed = harness._transcribe_voice_response(b"audio", None)

    assert transcription == "[voice message]"
    assert failed is True
    speech.recognize_from_file.assert_not_called()


def test_transcribe_voice_empty_transcription_marks_failure() -> None:
    speech = Mock()
    speech.is_available.return_value = True
    speech.recognize_from_file.return_value = "   "
    harness = _Harness(speech)

    transcription, failed = harness._transcribe_voice_response(b"audio", None)

    assert transcription == "[voice message]"
    assert failed is True


def test_transcribe_voice_exception_marks_failure() -> None:
    speech = Mock()
    speech.is_available.return_value = True
    speech.recognize_from_file.side_effect = RuntimeError("whisper crashed")
    harness = _Harness(speech)

    transcription, failed = harness._transcribe_voice_response(b"audio", None)

    assert transcription == "[voice message]"
    assert failed is True


def test_transcribe_voice_reuses_audio_path_without_cleanup() -> None:
    speech = Mock()
    speech.is_available.return_value = True
    speech.recognize_from_file.return_value = "hola"
    harness = _Harness(speech)

    transcription, failed = harness._transcribe_voice_response(None, "/tmp/streamed.wav")

    assert transcription == "hola"
    assert failed is False
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

    transcription, failed = harness._transcribe_voice_response(b"wav-bytes", None)

    assert transcription == "hola"
    assert failed is False
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
