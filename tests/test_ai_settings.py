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
