"""Regression tests for strict learning-provider behavior."""

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import UserSettings
from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app

client = TestClient(app)


@pytest.fixture
def configured_providers(
    setup_test_db,
    mock_llm_provider,
    mock_speech_provider,
):
    """Use a configured provider without contacting an external service."""
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_speech_provider] = lambda: mock_speech_provider
    yield mock_llm_provider
    app.dependency_overrides.clear()


def _start_session(user_id: int, token: str, topic: str = "animals") -> tuple[dict, int]:
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/learning/start",
        params={"user_id": user_id},
        json={"topic": topic, "purpose": "practice", "difficulty": "basic"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return headers, response.json()["session_id"]


@pytest.mark.usefixtures("setup_test_db")
def test_fenced_json_question_uses_llm_output(
    configured_providers, regular_user, user_token
):
    """Markdown fences are presentation noise, not a provider fallback."""
    configured_providers.generate.side_effect = None
    configured_providers.generate.return_value = (
        '```json\n{"question": "What does a cow say?",'
        ' "choices": ["Moo", "Meow", "Woof"], "correct": 0}\n```'
    )
    headers, session_id = _start_session(regular_user.id, user_token)

    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 200, question.text
    data = question.json()
    assert data["question_text"] == "What does a cow say?"
    assert data["choices"] == ["Moo", "Meow", "Woof"]
    assert data["correct_answer_index"] == 0


@pytest.mark.usefixtures("setup_test_db")
def test_question_retries_when_first_json_response_is_invalid(
    configured_providers, regular_user, user_token
):
    """A corrective retry repairs provider formatting without inventing data."""
    configured_providers.generate.side_effect = [
        "This is not JSON",
        '{"question": "What color is the sky?",'
        ' "choices": ["Blue", "Red", "Green"], "correct": 0}',
    ]
    headers, session_id = _start_session(regular_user.id, user_token)

    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 200, question.text
    data = question.json()
    assert data["question_text"] == "What color is the sky?"
    assert configured_providers.generate.call_count == 2
    retry_prompt = configured_providers.generate.call_args_list[1].kwargs["prompt"]
    assert "You must reply only with valid JSON" in retry_prompt


@pytest.mark.usefixtures("setup_test_db")
def test_question_returns_error_when_retry_is_still_invalid(
    configured_providers, regular_user, user_token
):
    """Invalid provider output is visible as an error after the retry budget."""
    configured_providers.generate.side_effect = ["not JSON", "still not JSON"]
    headers, session_id = _start_session(regular_user.id, user_token)

    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 400
    assert question.json()["detail"] == "LLM returned invalid question JSON after retry"


@pytest.mark.usefixtures("setup_test_db")
def test_question_returns_error_when_provider_is_unavailable(
    configured_providers, regular_user, user_token
):
    """A provider outage does not produce a deterministic question."""
    configured_providers.generate.side_effect = RuntimeError("LLM unavailable")
    headers, session_id = _start_session(regular_user.id, user_token)

    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 400
    assert question.json()["detail"] == "LLM question generation failed"


@pytest.mark.usefixtures("setup_test_db")
def test_conversational_provider_failure_is_explicit(
    configured_providers, regular_user, user_token, test_db_session
):
    """Conversation responses fail instead of returning a canned response."""
    test_db_session.add(UserSettings(user_id=regular_user.id, ui_language="en"))
    test_db_session.commit()
    headers, session_id = _start_session(regular_user.id, user_token)
    configured_providers.generate.side_effect = RuntimeError("LLM unavailable")

    response = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "Hello", "is_voice": False},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "LLM conversational response failed"
