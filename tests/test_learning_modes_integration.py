"""
Tests for Learning Modes integration and regression testing for session conflicts.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.aac_app.models.database import LearningMode
from src.api.dependencies import get_llm_provider, get_speech_provider, get_tts_provider
from src.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_providers(
    mock_llm_provider,
    mock_speech_provider,
    mock_tts_provider,
    test_db_session,
    monkeypatch,
):
    """Override provider dependencies with mocked versions"""
    from contextlib import contextmanager

    from src.aac_app import models
    from src.aac_app.services import achievement_system, learning_companion_service

    # Override providers
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_speech_provider] = lambda: mock_speech_provider
    app.dependency_overrides[get_tts_provider] = lambda: mock_tts_provider

    # Patch get_session to use test database in all modules that use it
    @contextmanager
    def mock_get_session():
        yield test_db_session

    monkeypatch.setattr(models.database, "get_session", mock_get_session)
    monkeypatch.setattr(learning_companion_service, "get_session", mock_get_session)
    monkeypatch.setattr(achievement_system, "get_session", mock_get_session)

    yield
    app.dependency_overrides.clear()


@pytest.mark.usefixtures("setup_test_db")
def test_learning_chat_with_custom_mode_regression(
    admin_user, admin_token, test_db_session: Session
):
    """
    Regression test for variable shadowing bug in learning_companion_service.
    
    The bug caused a session conflict when a LearningMode lookup (inner session)
    occurred within the process_response (outer session) block.
    """
    
    # 1. Create a custom Learning Mode
    # We can do this directly in DB or via API. Let's use DB to be fast.
    custom_mode = LearningMode(
        name="Regression Test Mode",
        key="regression_mode",
        description="A mode for testing regressions",
        prompt_instruction="Respond with 'Regression Test Passed'",
        created_by=admin_user.id,
        is_custom=True
    )
    test_db_session.add(custom_mode)
    test_db_session.commit()
    
    # 2. Start a session using this mode
    headers = {"Authorization": f"Bearer {admin_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "testing", "purpose": "regression_mode", "difficulty": "basic"},
        params={"user_id": admin_user.id},
        headers=headers,
    )
    
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]
    
    # 3. Send a message
    # This triggers process_response -> _get_system_prompt -> DB lookup for mode
    # If variable shadowing exists, this will fail with 500 or "Object attached to another session"
    answer_response = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "Hello test", "is_voice": False},
        headers=headers,
    )
    
    # 4. Verify success
    assert answer_response.status_code == 200
    data = answer_response.json()
    assert data["success"] is True
    # The mocked LLM should return something, we don't care exactly what, 
    # as long as the request succeeded without crashing.
