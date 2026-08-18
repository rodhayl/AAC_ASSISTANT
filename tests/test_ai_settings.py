"""
AI Settings API Tests

Tests for primary AI configuration endpoints
"""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


class TestPrimaryAISettings:
    """Test primary AI settings endpoints"""

    def test_get_ai_settings_default(self, admin_user, admin_token):
        """Test getting default AI settings"""
        response = client.get(
            "/api/settings/ai", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "ollama_model" in data
        assert "openrouter_model" in data
        assert "ollama_base_url" in data
        assert data["can_edit"] is True

    def test_get_ai_settings_student_no_edit(self, regular_user, user_token):
        """Test student can view but not edit AI settings"""
        response = client.get(
            "/api/settings/ai", headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["can_edit"] is False

    def test_update_ai_settings_ollama(self, admin_user, admin_token):
        """Test updating AI settings to Ollama"""
        response = client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider": "ollama",
                "ollama_model": "llama3.2:latest",
                "ollama_base_url": "http://localhost:11434",
            },
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Settings updated successfully"

        # Verify settings were saved
        verify_response = client.get(
            "/api/settings/ai", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert verify_response.status_code == 200
        data = verify_response.json()
        assert data["provider"] == "ollama"
        assert data["ollama_model"] == "llama3.2:latest"

    def test_update_ai_settings_openrouter(self, admin_user, admin_token):
        """Test updating AI settings to OpenRouter"""
        response = client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider": "openrouter",
                "openrouter_model": "openai/gpt-4",
                "openrouter_api_key": "sk-or-test-key",
            },
        )
        assert response.status_code == 200

        # Verify settings
        verify_response = client.get(
            "/api/settings/ai", headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = verify_response.json()
        assert data["provider"] == "openrouter"
        assert data["openrouter_model"] == "openai/gpt-4"

    def test_update_ai_settings_invalid_provider(self, admin_user, admin_token):
        """Test updating with invalid provider fails"""
        response = client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"provider": "invalid_provider", "ollama_model": "some-model"},
        )
        assert response.status_code == 400
        assert "must be 'ollama' or 'openrouter'" in response.json()["detail"]

    def test_invalid_later_field_rolls_back_all_settings(self, admin_user, admin_token):
        """A validation failure must not persist earlier fields from the same request."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        initial = client.put(
            "/api/settings/ai",
            headers=headers,
            json={
                "provider": "ollama",
                "ollama_model": "stable-model",
            },
        )
        assert initial.status_code == 200

        failed = client.put(
            "/api/settings/ai",
            headers=headers,
            json={
                "provider": "openrouter",
                "ollama_model": "partially-applied-model",
                "max_tokens": "not-a-positive-integer",
            },
        )
        assert failed.status_code == 400

        current = client.get("/api/settings/ai", headers=headers)
        assert current.status_code == 200
        assert current.json()["provider"] == "ollama"
        assert current.json()["ollama_model"] == "stable-model"

    def test_update_ai_settings_student_forbidden(self, regular_user, user_token):
        """Test student cannot update AI settings"""
        response = client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"provider": "ollama", "ollama_model": "llama3.2:latest"},
        )
        assert response.status_code == 403


class TestAISettingsAuthentication:
    """Test authentication requirements and removed settings routes."""

    def test_fallback_settings_endpoints_removed(self, admin_user, admin_token):
        """The deprecated fallback settings endpoints are no longer registered."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.get("/api/settings/ai/fallback", headers=headers).status_code in (404, 405)
        assert client.put("/api/settings/ai/fallback", headers=headers, json={}).status_code in (404, 405)

    def test_get_settings_no_auth(self):
        """Test getting settings without auth fails"""
        response = client.get("/api/settings/ai")
        assert response.status_code == 401

    def test_update_settings_no_auth(self):
        """Test updating settings without auth fails"""
        response = client.put(
            "/api/settings/ai", json={"provider": "ollama", "ollama_model": "test"}
        )
        assert response.status_code == 401


class TestSettingsValidationAndProviderModels:
    """Real-case coverage for behavior validation and provider model endpoints."""

    def test_update_ai_settings_rejects_non_positive_max_tokens(self, admin_user, admin_token):
        response = client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"provider": "ollama", "max_tokens": 0},
        )
        assert response.status_code == 400

    def test_update_ai_settings_rejects_out_of_range_temperature(self, admin_user, admin_token):
        response = client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"provider": "ollama", "temperature": 2.5},
        )
        assert response.status_code == 400

    def test_update_ai_settings_persists_behavior_values(self, admin_user, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = client.put(
            "/api/settings/ai",
            headers=headers,
            json={"provider": "ollama", "max_tokens": 2048, "temperature": 0.3},
        )
        assert response.status_code == 200

        data = client.get("/api/settings/ai", headers=headers).json()
        assert data["max_tokens"] == 2048
        assert data["temperature"] == 0.3

    def test_ui_language_defaults_to_spanish_without_settings(self, admin_user, admin_token):
        response = client.get(
            "/api/settings/ui", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert response.json()["ui_language"] == "es"

    def test_update_ui_language_round_trip(self, admin_user, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = client.put("/api/settings/ui", headers=headers, json={"ui_language": "en"})
        assert response.status_code == 200
        assert response.json()["ui_language"] == "en"

        data = client.get("/api/settings/ui", headers=headers).json()
        assert data["ui_language"] == "en"

    def test_update_ui_language_rejects_unsupported(self, admin_user, admin_token):
        response = client.put(
            "/api/settings/ui",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"ui_language": "fr"},
        )
        assert response.status_code == 400

    def test_get_ollama_models_unavailable_returns_503(self, admin_user, admin_token, monkeypatch):
        from unittest.mock import MagicMock

        mock_provider = MagicMock()
        mock_provider.is_available.return_value = False
        monkeypatch.setattr(
            "src.api.routers.settings.OllamaProvider", lambda **kwargs: mock_provider
        )
        response = client.get(
            "/api/settings/ai/models/ollama",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 503

    def test_get_ollama_models_success(self, admin_user, admin_token, monkeypatch):
        from unittest.mock import MagicMock

        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.list_models.return_value = ["llama3.2", "mistral"]
        monkeypatch.setattr(
            "src.api.routers.settings.OllamaProvider", lambda **kwargs: mock_provider
        )
        response = client.get(
            "/api/settings/ai/models/ollama",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["models"] == [{"name": "llama3.2"}, {"name": "mistral"}]

    def test_get_openrouter_models_requires_api_key(
        self, admin_user, admin_token
    ):
        response = client.get(
            "/api/settings/ai/models/openrouter",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400

    def test_get_openrouter_models_success(
        self, setup_test_db, test_db_session, admin_user, admin_token, monkeypatch
    ):
        from unittest.mock import AsyncMock, MagicMock

        from src.aac_app.models import AppSettings

        test_db_session.add(
            AppSettings(setting_key="openrouter_api_key", setting_value="sk-test-123")
        )
        test_db_session.commit()

        mock_provider = MagicMock()
        mock_provider.get_available_models = AsyncMock(
            return_value={"data": [{"id": "anthropic/claude-3.5-sonnet"}]}
        )
        monkeypatch.setattr(
            "src.api.routers.settings.OpenRouterProvider", lambda **kwargs: mock_provider
        )
        response = client.get(
            "/api/settings/ai/models/openrouter",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["models"][0]["id"] == "anthropic/claude-3.5-sonnet"

    def test_get_openrouter_models_uses_unsaved_request_key(
        self, setup_test_db, test_db_session, admin_user, admin_token, monkeypatch
    ):
        from unittest.mock import AsyncMock, MagicMock

        from src.aac_app.models import AppSettings

        test_db_session.add(
            AppSettings(setting_key="openrouter_api_key", setting_value="saved-key")
        )
        test_db_session.commit()

        mock_provider = MagicMock()
        mock_provider.get_available_models = AsyncMock(return_value={"data": []})
        provider_factory = MagicMock(return_value=mock_provider)
        monkeypatch.setattr(
            "src.api.routers.settings.OpenRouterProvider",
            provider_factory,
        )
        response = client.get(
            "/api/settings/ai/models/openrouter",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-OpenRouter-API-Key": "unsaved-key",
            },
        )

        assert response.status_code == 200
        provider_factory.assert_called_once_with(api_key="unsaved-key")
        assert mock_provider.get_available_models.await_count == 1

    def test_get_lmstudio_models_unavailable_returns_503(self, admin_user, admin_token, monkeypatch):
        from unittest.mock import MagicMock

        mock_provider = MagicMock()
        mock_provider.is_available.return_value = False
        monkeypatch.setattr(
            "src.api.routers.settings.LMStudioProvider", lambda **kwargs: mock_provider
        )
        response = client.get(
            "/api/settings/ai/models/lmstudio",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 503

    def test_get_lmstudio_models_success(self, admin_user, admin_token, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.get_available_models = AsyncMock(
            return_value={"data": [{"id": "local-model"}]}
        )
        monkeypatch.setattr(
            "src.api.routers.settings.LMStudioProvider", lambda **kwargs: mock_provider
        )
        response = client.get(
            "/api/settings/ai/models/lmstudio",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["models"] == [{"id": "local-model"}]
