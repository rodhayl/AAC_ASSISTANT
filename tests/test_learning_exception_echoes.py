"""Regression tests: learning services never echo raw exceptions to clients.

The three public service methods that can surface an error to the client
(``ask_question``, ``end_learning_session``, ``process_response``) must
return a stable message when their provider crashes.  The full exception is
kept in the server log; leaking it would expose internals (connection
strings, filesystem paths, tracebacks) through the API ``detail`` field.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from loguru import logger

from src.aac_app.models import LearningSession
from src.aac_app.services.learning.service import LearningCompanionService


def _active_session(test_db_session, user_id: int) -> LearningSession:
    session = LearningSession(
        user_id=user_id,
        topic_name="Weather",
        purpose="",
        status="active",
        conversation_history=[],
        comprehension_score=0.5,
        questions_answered=2,
        correct_answers=1,
    )
    test_db_session.add(session)
    test_db_session.commit()
    test_db_session.refresh(session)
    return session


_RAW_CRASH = (
    "connection refused: postgres://svc:supersecret@internal-01:5432/aac"
)


def _crashing_generate() -> AsyncMock:
    return AsyncMock(side_effect=RuntimeError(_RAW_CRASH))


def test_ask_question_never_echoes_raw_exception(
    test_db_session, regular_user, mock_llm_provider, mock_speech_provider
):
    """A crashing provider during question generation yields a stable error."""
    session = _active_session(test_db_session, regular_user.id)
    mock_llm_provider.generate = _crashing_generate()
    service = LearningCompanionService(mock_llm_provider, mock_speech_provider)

    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(str(message)), level="ERROR")
    try:
        result = asyncio.run(
            service.ask_question(session_id=session.id, db=test_db_session)
        )
    finally:
        logger.remove(sink_id)

    assert result == {"success": False, "error": "Failed to generate question"}
    # The raw detail is not echoed to the client; the server log records the
    # failure (the inner provider wrapper re-raises a stable cause message).
    assert "internal-01" not in str(result)
    assert "supersecret" not in str(result)
    assert any("Failed to generate question" in message for message in captured)


def test_end_learning_session_never_echoes_raw_exception(
    test_db_session, regular_user, mock_llm_provider, mock_speech_provider
):
    """A crashing provider during summarization yields a stable error."""
    session = _active_session(test_db_session, regular_user.id)
    mock_llm_provider.generate = _crashing_generate()
    service = LearningCompanionService(mock_llm_provider, mock_speech_provider)

    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(str(message)), level="ERROR")
    try:
        result = asyncio.run(
            service.end_learning_session(session_id=session.id, db=test_db_session)
        )
    finally:
        logger.remove(sink_id)

    assert result == {"success": False, "error": "Failed to end learning session"}
    # The raw detail is not echoed to the client but stays in the server log.
    assert "internal-01" not in str(result)
    assert "supersecret" not in str(result)
    assert any(_RAW_CRASH in message for message in captured)
