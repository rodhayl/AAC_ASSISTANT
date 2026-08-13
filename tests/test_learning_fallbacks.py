"""Regression tests for learning flows without a reachable LLM."""

import re

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import UserSettings
from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app

client = TestClient(app)


def _is_raw_translation_key(value: str) -> bool:
    """Match the dot-notation keys returned when a locale lookup fails."""
    return bool(re.fullmatch(r"[a-zA-Z][\w]*(\.[\w]+)+", value))


@pytest.fixture
def fallback_providers(
    setup_test_db,
    mock_llm_provider,
    mock_speech_provider,
):
    """Make every learning request use the graceful-degradation path."""
    mock_llm_provider.generate.side_effect = RuntimeError("LLM unavailable")
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_speech_provider] = lambda: mock_speech_provider
    yield
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
@pytest.mark.parametrize("language", ["en", "es"])
def test_fallback_question_and_feedback_are_localized(
    fallback_providers, regular_user, user_token, test_db_session, language
):
    """Fallback question and response feedback must be human-readable in both locales."""
    test_db_session.add(UserSettings(user_id=regular_user.id, ui_language=language))
    test_db_session.commit()
    headers, session_id = _start_session(regular_user.id, user_token)

    question = client.post(
        f"/api/learning/{session_id}/ask",
        headers=headers,
    )

    assert question.status_code == 200, question.text
    question_data = question.json()
    assert question_data["success"] is True
    assert " " in question_data["question_text"]
    assert len(question_data["choices"]) >= 3
    assert question_data["correct_answer_index"] == 0
    assert not _is_raw_translation_key(question_data["question_text"])
    assert all(" " in choice for choice in question_data["choices"])

    answer = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "not the expected choice", "is_voice": False},
        headers=headers,
    )

    assert answer.status_code == 200, answer.text
    answer_data = answer.json()
    assert answer_data["success"] is True
    assert " " in answer_data["feedback_message"]
    assert not _is_raw_translation_key(answer_data["feedback_message"])


def test_fallback_question_grading_is_deterministic(fallback_providers, regular_user, user_token):
    """The fallback choice is graded exactly, and progress uses a running average."""
    headers, session_id = _start_session(regular_user.id, user_token)

    first_question = client.post(f"/api/learning/{session_id}/ask", headers=headers).json()
    correct_answer = first_question["choices"][first_question["correct_answer_index"]]
    correct = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": correct_answer, "is_voice": False},
        headers=headers,
    )

    assert correct.status_code == 200, correct.text
    assert correct.json()["is_correct"] is True
    progress_after_correct = client.get(
        f"/api/learning/{session_id}/progress", headers=headers
    ).json()
    assert progress_after_correct["questions_asked"] == 1
    assert progress_after_correct["questions_answered"] == 1
    assert progress_after_correct["correct_answers"] == 1
    assert progress_after_correct["comprehension_score"] == 1.0

    second_question = client.post(f"/api/learning/{session_id}/ask", headers=headers).json()
    wrong = client.post(
        f"/api/learning/{session_id}/answer",
        json={
            "answer": second_question["choices"][1],
            "is_voice": False,
        },
        headers=headers,
    )

    assert wrong.status_code == 200, wrong.text
    assert wrong.json()["is_correct"] is False
    progress_after_wrong = client.get(
        f"/api/learning/{session_id}/progress", headers=headers
    ).json()
    assert progress_after_wrong["questions_asked"] == 2
    assert progress_after_wrong["questions_answered"] == 2
    assert progress_after_wrong["correct_answers"] == 1
    assert progress_after_wrong["comprehension_score"] == 0.5


@pytest.mark.parametrize(
    ("language", "expected_feedback"),
    [
        ("en", "Good try! Keep practicing and you will improve."),
        ("es", "¡Buen intento! Sigue practicando y mejorarás."),
    ],
)
def test_missing_encouraging_feedback_uses_localized_fallback(
    fallback_providers,
    mock_llm_provider,
    regular_user,
    user_token,
    test_db_session,
    language,
    expected_feedback,
):
    """A response without LLM feedback still returns the user's localized message."""
    test_db_session.add(UserSettings(user_id=regular_user.id, ui_language=language))
    test_db_session.commit()
    headers, session_id = _start_session(regular_user.id, user_token)

    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)
    assert question.status_code == 200, question.text

    mock_llm_provider.generate.side_effect = None
    mock_llm_provider.generate.return_value = '{"is_correct": false, "confidence": 0.5}'
    answer = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "not the expected choice", "is_voice": False},
        headers=headers,
    )

    assert answer.status_code == 200, answer.text
    assert answer.json()["feedback_message"] == expected_feedback


def test_fenced_json_question_uses_llm_output_not_fallback(
    fallback_providers, mock_llm_provider, regular_user, user_token
):
    """A fenced-JSON LLM response is parsed and used instead of the fallback."""
    headers, session_id = _start_session(regular_user.id, user_token)

    mock_llm_provider.generate.side_effect = None
    mock_llm_provider.generate.return_value = (
        '```json\n{"question": "What does a cow say?",'
        ' "choices": ["Moo", "Meow", "Woof"], "correct": 0}\n```'
    )
    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 200, question.text
    data = question.json()
    assert data["success"] is True
    assert data["question_text"] == "What does a cow say?"
    assert data["choices"] == ["Moo", "Meow", "Woof"]
    assert data["correct_answer_index"] == 0


def test_question_retries_with_strict_json_when_first_response_invalid(
    fallback_providers, mock_llm_provider, regular_user, user_token
):
    """A non-JSON first reply triggers a corrective strict-JSON retry."""
    headers, session_id = _start_session(regular_user.id, user_token)

    mock_llm_provider.generate.side_effect = [
        "¡Hola! Es un gusto saludarte. ¡Vamos a practicar juntos!",
        '{"question": "What color is the sky?",'
        ' "choices": ["Blue", "Red", "Green"], "correct": 0}',
    ]
    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 200, question.text
    data = question.json()
    assert data["success"] is True
    assert data["question_text"] == "What color is the sky?"
    assert data["choices"] == ["Blue", "Red", "Green"]
    assert mock_llm_provider.generate.call_count == 2

    # The corrective retry must demand strict JSON and echo the failed reply
    retry_prompt = mock_llm_provider.generate.call_args_list[1].kwargs["prompt"]
    assert "You must reply only with valid JSON" in retry_prompt
    assert "¡Hola! Es un gusto saludarte" in retry_prompt
    assert mock_llm_provider.generate.call_args_list[1].kwargs["temperature"] == 0.2


def test_question_falls_back_when_retry_also_invalid(
    fallback_providers, mock_llm_provider, regular_user, user_token
):
    """If both attempts return non-JSON, the translated fallback question is used."""
    headers, session_id = _start_session(regular_user.id, user_token)

    mock_llm_provider.generate.side_effect = [
        "¡Hola! ¿Cómo estás hoy?",
        "Claro, aquí tienes la respuesta: el elefante es muy grande",
    ]
    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 200, question.text
    data = question.json()
    assert data["success"] is True
    assert " " in data["question_text"]
    assert len(data["choices"]) >= 3
    assert mock_llm_provider.generate.call_count == 2


def test_question_falls_back_when_retry_json_missing_fields(
    fallback_providers, mock_llm_provider, regular_user, user_token
):
    """A retry that parses to JSON but lacks required fields uses the fallback."""
    headers, session_id = _start_session(regular_user.id, user_token)

    mock_llm_provider.generate.side_effect = [
        "¡Hola! ¿Cómo estás hoy?",
        '{"response": "just a chatty answer, not a question"}',
    ]
    question = client.post(f"/api/learning/{session_id}/ask", headers=headers)

    assert question.status_code == 200, question.text
    data = question.json()
    assert data["success"] is True
    assert " " in data["question_text"]
    assert len(data["choices"]) >= 3
    assert mock_llm_provider.generate.call_count == 2


def test_end_without_llm_returns_summary_and_awards_first_steps(
    fallback_providers, regular_user, user_token
):
    """Ending a fallback session returns statistics and triggers First Steps."""
    headers, session_id = _start_session(regular_user.id, user_token)
    answer = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "I like dogs", "is_voice": False},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text

    ended = client.post(f"/api/learning/{session_id}/end", headers=headers)

    assert ended.status_code == 200, ended.text
    ended_data = ended.json()
    assert ended_data["success"] is True
    assert ended_data["summary"]
    assert ended_data["statistics"]["questions_answered"] == 0
    assert ended_data["statistics"]["correct_answers"] == 0

    progress = client.get(f"/api/learning/{session_id}/progress", headers=headers)
    assert progress.status_code == 200
    assert progress.json()["status"] == "completed"

    achievements = client.get(f"/api/achievements/user/{regular_user.id}", headers=headers)
    assert achievements.status_code == 200, achievements.text
    first_steps = next(
        achievement for achievement in achievements.json() if achievement["name"] == "First Steps"
    )
    assert first_steps["earned_at"] is not None

    points = client.get(f"/api/achievements/user/{regular_user.id}/points", headers=headers)
    assert points.status_code == 200, points.text
    assert points.json() == 10
