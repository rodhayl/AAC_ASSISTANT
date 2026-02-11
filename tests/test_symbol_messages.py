"""
End-to-end tests for symbol-first (AAC symbol) submissions.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock

from src.api.main import app
from src.api.dependencies import get_learning_service
from src.aac_app.services.learning_companion_service import LearningCompanionService
from src.aac_app.models.database import LearningSession


client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


@pytest.fixture
def override_learning_service():
    """
    Override the learning service dependency with a mock LLM/TTS so tests
    don't require real providers.
    """
    llm = Mock()
    llm.generate = AsyncMock(return_value="Mock tutor reply.")
    speech = Mock()
    tts = Mock()

    service = LearningCompanionService(
        llm_provider=llm,
        speech_provider=speech,
        tts_provider=tts,
        default_max_tokens=256,
        default_temperature=0.4,
    )

    def _get_service():
        return service

    app.dependency_overrides[get_learning_service] = _get_service
    yield
    app.dependency_overrides.pop(get_learning_service, None)


def test_symbol_answer_stores_metadata_and_marks_mode(test_db_session, admin_user, admin_token, override_learning_service):
    """Posting symbols should succeed and persist mode='symbol' with symbol metadata."""
    # Start a session
    start = client.post(
        "/api/learning/start",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"topic": "symbols demo", "purpose": "aac", "difficulty": "basic"},
        params={"user_id": 1},
    )
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    # Send symbols
    symbols_payload = {
        "symbols": [
            {"id": 1, "label": "I", "category": "pronouns"},
            {"id": 2, "label": "want", "category": "actions"},
            {"id": 3, "label": "juice", "category": "food"},
        ]
    }
    resp = client.post(
        f"/api/learning/{session_id}/answer/symbols",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=symbols_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Verify conversation history contains the symbol response with mode and symbols
    session = test_db_session.query(LearningSession).filter_by(id=session_id).first()
    assert session is not None
    history = session.conversation_history
    # Should have at least one entry (the symbol message)
    assert any(
        entry.get("mode") == "symbol" and len(entry.get("symbols") or []) == 3
        for entry in history
    )
