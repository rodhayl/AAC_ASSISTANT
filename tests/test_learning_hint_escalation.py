"""Hint-escalation policy for wrong answers and anti-leak question prompts.

Pedagogy contract: the tutor must not hand the student the exact target word
up front. Wrong attempts get progressive hints; the full correct answer is
only revealed from ``REVEAL_ANSWER_ATTEMPT`` onwards, and the response tells
the UI (``answer_revealed``) when it may auto-advance to a new question.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app

client = TestClient(app)

QUESTION_JSON = (
    '{"question": "What do you say when you see a friend in the morning?",'
    ' "choices": ["Good morning", "Goodbye", "Thanks"], "correct": 0}'
)
WRONG_JSON = (
    '{"is_correct": false, "confidence": 0.9,'
    ' "encouraging_feedback": "Almost! Think about the morning."}'
)
CORRECT_JSON = (
    '{"is_correct": true, "confidence": 1.0,'
    ' "encouraging_feedback": "Great job!"}'
)


@pytest.fixture
def configured_providers(setup_test_db, mock_llm_provider, mock_speech_provider):
    """Use a configured provider without contacting an external service."""
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_speech_provider] = lambda: mock_speech_provider
    yield mock_llm_provider
    app.dependency_overrides.clear()


def _start_session(user_id: int, token: str) -> tuple[dict, int]:
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/learning/start",
        params={"user_id": user_id},
        json={"topic": "greetings", "purpose": "practice", "difficulty": "basic"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return headers, response.json()["session_id"]


def _answer(session_id: int, headers: dict, answer: str) -> dict:
    response = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": answer},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.usefixtures("setup_test_db")
def test_question_prompt_forbids_leaking_the_correct_answer(
    configured_providers, regular_user, user_token
):
    """The question prompt must forbid putting the answer in the question."""
    configured_providers.generate.side_effect = None
    configured_providers.generate.return_value = QUESTION_JSON
    headers, session_id = _start_session(regular_user.id, user_token)

    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 200, question.text
    prompt = configured_providers.generate.call_args.kwargs["prompt"]
    assert "Never include the correct answer" in prompt
    assert "plausible, topic-related alternatives" in prompt


@pytest.mark.usefixtures("setup_test_db")
def test_first_wrong_answer_gets_a_hint_without_revealing(
    configured_providers, regular_user, user_token
):
    """Attempt 1: the prompt forbids naming the answer; no auto-advance flag."""
    configured_providers.generate.side_effect = [QUESTION_JSON, WRONG_JSON]
    headers, session_id = _start_session(regular_user.id, user_token)
    client.post(f"/api/learning/{session_id}/ask", headers=headers)

    result = _answer(session_id, headers, "Goodbye")

    assert result["is_correct"] is False
    assert result["answer_revealed"] is False
    analysis_prompt = configured_providers.generate.call_args.kwargs["prompt"]
    assert "Attempt number for this question: 1" in analysis_prompt
    assert "do NOT say or name the correct answer" in analysis_prompt


@pytest.mark.usefixtures("setup_test_db")
def test_third_wrong_attempt_may_reveal_and_lets_ui_advance(
    configured_providers, regular_user, user_token
):
    """Attempts 1-2 keep hints; attempt 3 may reveal and sets the flag."""
    configured_providers.generate.side_effect = [
        QUESTION_JSON,
        WRONG_JSON,
        WRONG_JSON,
        WRONG_JSON,
    ]
    headers, session_id = _start_session(regular_user.id, user_token)
    client.post(f"/api/learning/{session_id}/ask", headers=headers)

    first = _answer(session_id, headers, "Goodbye")
    second = _answer(session_id, headers, "Thanks")
    third = _answer(session_id, headers, "I do not know")

    assert first["answer_revealed"] is False
    assert second["answer_revealed"] is False
    assert third["answer_revealed"] is True
    prompts = [
        call.kwargs["prompt"]
        for call in configured_providers.generate.call_args_list[1:]
    ]
    assert "Attempt number for this question: 1" in prompts[0]
    assert "Attempt number for this question: 2" in prompts[1]
    assert "Attempt number for this question: 3" in prompts[2]
    assert "stronger hint" in prompts[1]
    assert "you may gently say the correct answer" in prompts[2]


@pytest.mark.usefixtures("setup_test_db")
def test_question_prompt_prioritizes_unpracticed_terms(
    configured_providers, regular_user, user_token
):
    """The next question sees what was already asked, and a fresh session on
    the same topic inherits terms practiced in earlier sessions."""
    configured_providers.generate.side_effect = [
        QUESTION_JSON,  # session A: first question
        CORRECT_JSON,  # session A: student masters "Good morning"
        QUESTION_JSON,  # session A: next question
        QUESTION_JSON,  # session B: first question
    ]
    headers, session_a = _start_session(regular_user.id, user_token)
    client.post(f"/api/learning/{session_a}/ask", headers=headers)
    _answer(session_a, headers, "Good morning")
    client.post(f"/api/learning/{session_a}/ask", headers=headers)

    second_prompt = configured_providers.generate.call_args_list[2].kwargs["prompt"]
    assert "Questions already asked in this session" in second_prompt
    assert "What do you say when you see a friend in the morning?" in second_prompt
    assert "prioritize vocabulary" in second_prompt

    headers_b, session_b = _start_session(regular_user.id, user_token)
    client.post(f"/api/learning/{session_b}/ask", headers=headers_b)

    third_prompt = configured_providers.generate.call_args_list[3].kwargs["prompt"]
    assert "already practiced in recent sessions" in third_prompt
    assert "Good morning" in third_prompt


@pytest.mark.usefixtures("setup_test_db")
def test_correct_answer_never_sets_the_reveal_flag(
    configured_providers, regular_user, user_token
):
    """A correct answer does not need the reveal flag to advance."""
    configured_providers.generate.side_effect = [QUESTION_JSON, CORRECT_JSON]
    headers, session_id = _start_session(regular_user.id, user_token)
    client.post(f"/api/learning/{session_id}/ask", headers=headers)

    result = _answer(session_id, headers, "Good morning")

    assert result["is_correct"] is True
    assert result["answer_revealed"] is False
