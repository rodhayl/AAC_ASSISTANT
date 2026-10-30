"""
End-to-end tests for LLM behavior settings.

These tests verify that:
- max_tokens and temperature are exposed via the settings API
- get_learning_service wires settings into LearningCompanionService defaults
- LearningCompanionService passes those defaults through to the LLM provider
"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import LearningSession, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.learning_companion_service import LearningCompanionService
from src.api import dependencies as deps
from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)


pytestmark = pytest.mark.usefixtures("setup_test_db")


@pytest.fixture
def admin_username(test_db_session):
    """Create an admin user and return user info tuple (id, username, user_type)."""
    admin = User(
        username="admin_llm_behavior",
        password_hash=get_password_hash("AdminPassword123"),
        display_name="Admin Behavior",
        user_type="admin",
    )
    test_db_session.add(admin)
    test_db_session.commit()
    test_db_session.refresh(admin)
    return (admin.id, admin.username, admin.user_type)


class DummyOllama(deps.OllamaProvider):
    """Lightweight Ollama subclass that skips HTTP setup for config tests."""

    def __init__(self):  # pragma: no cover - trivial test helper
        # Do not call super().__init__ to avoid HTTP client construction
        pass


class DummyOpenRouter(deps.OpenRouterProvider):
    """Lightweight OpenRouter subclass that skips HTTP setup for config tests."""

    def __init__(self):  # pragma: no cover - trivial test helper
        pass


def test_primary_behavior_settings_exposed_and_persisted(admin_username):
    """Primary AI settings include behavior fields and round-trip correctly."""
    user_id, username, user_type = admin_username
    headers = create_test_headers(user_id, username, user_type)

    # Default read
    resp = client.get(
        "/api/settings/ai",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_tokens"] == 1024
    assert pytest.approx(data["temperature"], rel=1e-6) == 0.5

    # Update behavior
    update = client.put(
        "/api/settings/ai",
        headers=headers,
        json={
            "provider": "ollama",
            "ollama_model": "llama3.2:latest",
            "max_tokens": 2048,
            "temperature": 0.6,
        },
    )
    assert update.status_code == 200

    # Verify persisted
    verify = client.get(
        "/api/settings/ai",
        headers=headers,
    )
    data = verify.json()
    assert data["max_tokens"] == 2048
    assert pytest.approx(data["temperature"], rel=1e-6) == 0.6


def test_fallback_behavior_settings_exposed_and_persisted(admin_username):
    """Fallback AI settings include behavior fields and round-trip correctly."""
    user_id, username, user_type = admin_username
    headers = create_test_headers(user_id, username, user_type)

    resp = client.get(
        "/api/settings/ai/fallback",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_tokens"] == 1024
    assert pytest.approx(data["temperature"], rel=1e-6) == 0.5

    update = client.put(
        "/api/settings/ai/fallback",
        headers=headers,
        json={
            "provider": "openrouter",
            "openrouter_model": "openai/gpt-4",
            "max_tokens": 512,
            "temperature": 0.4,
        },
    )
    assert update.status_code == 200

    verify = client.get(
        "/api/settings/ai/fallback",
        headers=headers,
    )
    data = verify.json()
    assert data["max_tokens"] == 512
    assert pytest.approx(data["temperature"], rel=1e-6) == 0.4


def test_get_learning_service_uses_primary_behavior_settings(monkeypatch):
    """get_learning_service wires ai_max_tokens/ai_temperature into the service defaults."""

    def fake_get_setting(key: str, default: str = "") -> str:
        mapping = {
            "ai_provider": "ollama",
            "ai_max_tokens": "2048",
            "ai_temperature": "0.6",
            # No fallback overrides
        }
        return mapping.get(key, default)

    monkeypatch.setattr(deps, "get_setting_value", fake_get_setting)

    llm = DummyOllama()
    speech = Mock()
    tts = Mock()

    service = deps.get_learning_service(llm=llm, speech=speech, tts=tts)
    assert isinstance(service, LearningCompanionService)
    assert service.default_max_tokens == 2048
    assert pytest.approx(service.default_temperature, rel=1e-6) == 0.6


def test_get_learning_service_uses_fallback_behavior_for_openrouter(monkeypatch):
    """
    When the active provider is OpenRouter and fallback settings are defined
    for openrouter, get_learning_service should use the fallback behavior values.
    """

    def fake_get_setting(key: str, default: str = "") -> str:
        mapping = {
            "ai_provider": "ollama",
            "ai_max_tokens": "1024",
            "ai_temperature": "0.5",
            "fallback_ai_provider": "openrouter",
            "fallback_ai_max_tokens": "256",
            "fallback_ai_temperature": "0.3",
        }
        return mapping.get(key, default)

    monkeypatch.setattr(deps, "get_setting_value", fake_get_setting)

    llm = DummyOpenRouter()
    speech = Mock()
    tts = Mock()

    service = deps.get_learning_service(llm=llm, speech=speech, tts=tts)
    assert isinstance(service, LearningCompanionService)
    # Should pick fallback values, not primary
    assert service.default_max_tokens == 256
    assert pytest.approx(service.default_temperature, rel=1e-6) == 0.3


@pytest.mark.anyio
async def test_learning_service_passes_defaults_to_llm_generate_in_conversation(
    test_db_session,
):
    """
    Full flow through LearningCompanionService: ensure default_max_tokens and
    default_temperature are forwarded into llm.generate for conversational replies.
    """
    from unittest.mock import AsyncMock

    # Create a test user
    user = User(
        username="student_behavior",
        password_hash=get_password_hash("StudentPassword123"),
        display_name="Student",
        user_type="student",
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    # Create a simple active learning session with empty conversation history
    session = LearningSession(
        user_id=user.id,
        topic_name="general conversation",
        purpose="practice",
        status="active",
        conversation_history=[],
    )
    test_db_session.add(session)
    test_db_session.commit()
    test_db_session.refresh(session)

    # Mock LLM with AsyncMock so we can inspect call arguments
    llm = Mock()
    llm.generate = AsyncMock(return_value="Tutor reply.")

    speech = Mock()
    tts = Mock()

    # Configure explicit defaults so the test is deterministic
    service = LearningCompanionService(
        llm_provider=llm,
        speech_provider=speech,
        tts_provider=tts,
        default_max_tokens=512,
        default_temperature=0.4,
    )

    # Call process_response in conversational mode (no last_question)
    await service.process_response(
        session_id=session.id,
        student_response="What can you tell me about AAC?",
        is_voice=False,
    )

    # The last call to llm.generate should use our defaults
    assert llm.generate.call_count >= 1
    _, kwargs = llm.generate.call_args
    assert kwargs.get("max_tokens") == 512
    assert pytest.approx(kwargs.get("temperature"), rel=1e-6) == 0.4
