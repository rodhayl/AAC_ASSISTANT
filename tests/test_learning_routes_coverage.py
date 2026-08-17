"""Real-case API coverage for the learning router (src/api/routers/learning.py).

Covers permission denials, service-failure -> HTTP error mappings, the voice
answer upload path, and symbol-answer validation, all with a mocked learning
service so no LLM or speech engine is required.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_learning_service
from src.api.main import app

client = TestClient(app)

WAV_FIXTURE = Path(__file__).parent / "fixtures" / "voice_sample.wav"


@pytest.fixture
def mock_learning_service():
    service = MagicMock()
    service.start_learning_session = MagicMock(
        return_value={"success": True, "session_id": 1}
    )
    service.ask_question = AsyncMock(return_value={"success": True})
    service.process_response = AsyncMock(return_value={"success": True})
    service.end_learning_session = AsyncMock(return_value={"success": True})
    service.get_session_progress = MagicMock(
        return_value={"success": True, "progress": 50}
    )
    service.get_user_history = MagicMock(return_value={"success": True, "sessions": []})
    return service


@pytest.fixture(autouse=True)
def _override_learning_service(mock_learning_service, setup_test_db):
    """Route the learning router through a mock service (no LLM or speech)."""
    app.dependency_overrides[get_learning_service] = lambda: mock_learning_service
    yield
    app.dependency_overrides.pop(get_learning_service, None)


@pytest.fixture
def learning_session(test_db_session, admin_user) -> int:
    """A real persisted session so the owner/admin session check passes."""
    from src.aac_app.models import LearningSession

    session = LearningSession(user_id=admin_user.id, topic_name="Weather")
    test_db_session.add(session)
    test_db_session.commit()
    test_db_session.refresh(session)
    return session.id


@pytest.fixture
def admin_headers(admin_user, admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def user_headers(regular_user, user_token):
    return {"Authorization": f"Bearer {user_token}"}


def test_start_session_forbidden_for_other_user(admin_user, user_headers):
    """A non-admin cannot start a session on behalf of another user (403)."""
    response = client.post(
        f"/api/learning/start?user_id={admin_user.id}",
        headers=user_headers,
        json={"topic": "Weather"},
    )
    assert response.status_code == 403


def test_start_session_failure_maps_to_400(
    admin_user, admin_headers, mock_learning_service
):
    mock_learning_service.start_learning_session.return_value = {
        "success": False,
        "error": "session already active",
    }
    response = client.post(
        f"/api/learning/start?user_id={admin_user.id}",
        headers=admin_headers,
        json={"topic": "Weather"},
    )
    assert response.status_code == 400
    assert "already active" in response.json()["detail"]


def test_ask_question_failure_maps_to_400(
    admin_headers, mock_learning_service, learning_session
):
    mock_learning_service.ask_question.return_value = {
        "success": False,
        "error": "no question available",
    }
    response = client.post(
        f"/api/learning/{learning_session}/ask", headers=admin_headers, json={}
    )
    assert response.status_code == 400


def test_submit_answer_failure_maps_to_400(
    admin_headers, mock_learning_service, learning_session
):
    mock_learning_service.process_response.return_value = {
        "success": False,
        "error": "grading failed",
    }
    response = client.post(
        f"/api/learning/{learning_session}/answer",
        headers=admin_headers,
        json={"answer": "the sky"},
    )
    assert response.status_code == 400


def test_submit_voice_answer_success_uploads_audio(
    admin_user, admin_headers, mock_learning_service, learning_session
):
    """A valid WAV upload is saved, transcribed via the service, and returns 200."""
    mock_learning_service.process_response.return_value = {
        "success": True,
        "transcription": "hola",
        "feedback_message": "Bien hecho",
    }
    with WAV_FIXTURE.open("rb") as f:
        response = client.post(
            f"/api/learning/{learning_session}/answer/voice",
            headers=admin_headers,
            files={"file": ("voice.wav", f, "audio/wav")},
        )
    assert response.status_code == 200
    assert response.json()["transcription"] == "hola"
    mock_learning_service.process_response.assert_awaited_once()
    # The audio path is passed for transcription and removed afterwards.
    _, kwargs = mock_learning_service.process_response.await_args
    assert kwargs["is_voice"] is True
    assert kwargs["audio_path"] is not None
    assert not Path(kwargs["audio_path"]).exists()


def test_symbol_answer_requires_symbols(admin_headers, learning_session):
    response = client.post(
        f"/api/learning/{learning_session}/answer/symbols",
        headers=admin_headers,
        json={"symbols": []},
    )
    assert response.status_code == 400


def test_symbol_answer_joins_labels_without_gloss(
    admin_headers, mock_learning_service, learning_session
):
    mock_learning_service.process_response.return_value = {"success": True}
    response = client.post(
        f"/api/learning/{learning_session}/answer/symbols",
        headers=admin_headers,
        json={"symbols": [{"label": "Quiero"}, {"label": "agua"}]},
    )
    assert response.status_code == 200
    _, kwargs = mock_learning_service.process_response.await_args
    assert kwargs["student_response"] == "Quiero agua"


def test_end_session_failure_maps_to_400(
    admin_headers, mock_learning_service, learning_session
):
    mock_learning_service.end_learning_session.return_value = {
        "success": False,
        "error": "session ended already",
    }
    response = client.post(f"/api/learning/{learning_session}/end", headers=admin_headers)
    assert response.status_code == 400


def test_get_progress_failure_maps_to_404(
    admin_headers, mock_learning_service, learning_session
):
    mock_learning_service.get_session_progress.return_value = {
        "success": False,
        "error": "session not found",
    }
    response = client.get(
        f"/api/learning/{learning_session}/progress", headers=admin_headers
    )
    assert response.status_code == 404


def test_get_history_forbidden_for_other_user(admin_user, user_headers):
    response = client.get(
        f"/api/learning/history/{admin_user.id}", headers=user_headers
    )
    assert response.status_code == 403


def test_get_history_failure_maps_to_400(admin_headers, mock_learning_service):
    mock_learning_service.get_user_history.return_value = {
        "success": False,
        "error": "no history",
    }
    response = client.get(
        "/api/learning/history/1", headers=admin_headers
    )
    assert response.status_code == 400
