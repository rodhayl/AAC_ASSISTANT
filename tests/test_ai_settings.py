"""
AI Settings API Tests

Tests for primary and fallback AI configuration endpoints
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

    def test_update_ai_settings_student_forbidden(self, regular_user, user_token):
        """Test student cannot update AI settings"""
        response = client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"provider": "ollama", "ollama_model": "llama3.2:latest"},
        )
        assert response.status_code == 403


class TestFallbackAISettings:
    """Test fallback AI settings endpoints"""

    def test_get_fallback_settings_default(self, admin_user, admin_token):
        """Test getting default fallback AI settings"""
        response = client.get(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "ollama_model" in data
        assert "openrouter_model" in data
        assert "ollama_base_url" in data
        assert data["can_edit"] is True

    def test_update_fallback_settings_ollama(self, admin_user, admin_token):
        """Test updating fallback settings to Ollama"""
        response = client.put(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider": "ollama",
                "ollama_model": "mistral:latest",
                "ollama_base_url": "http://localhost:11434",
            },
        )
        assert response.status_code == 200
        assert "Fallback settings updated successfully" in response.json()["message"]

        # Verify fallback settings were saved
        verify_response = client.get(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = verify_response.json()
        assert data["provider"] == "ollama"
        assert data["ollama_model"] == "mistral:latest"

    def test_update_fallback_settings_openrouter(self, admin_user, admin_token):
        """Test updating fallback settings to OpenRouter"""
        response = client.put(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider": "openrouter",
                "openrouter_model": "anthropic/claude-3-sonnet",
                "openrouter_api_key": "sk-or-fallback-key",
            },
        )
        assert response.status_code == 200

        # Verify fallback settings
        verify_response = client.get(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = verify_response.json()
        assert data["provider"] == "openrouter"
        assert data["openrouter_model"] == "anthropic/claude-3-sonnet"

    def test_fallback_independent_from_primary(self, admin_user, admin_token):
        """Test that fallback settings don't affect primary settings"""
        # Set primary
        client.put(
            "/api/settings/ai",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"provider": "ollama", "ollama_model": "llama3.2:latest"},
        )

        # Set fallback
        client.put(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"provider": "openrouter", "openrouter_model": "openai/gpt-4"},
        )

        # Verify primary unchanged
        primary = client.get(
            "/api/settings/ai", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert primary["provider"] == "ollama"
        assert primary["ollama_model"] == "llama3.2:latest"

        # Verify fallback is different
        fallback = client.get(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert fallback["provider"] == "openrouter"
        assert fallback["openrouter_model"] == "openai/gpt-4"

    def test_update_fallback_invalid_provider(self, admin_user, admin_token):
        """Test updating fallback with invalid provider fails"""
        response = client.put(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"provider": "invalid_provider", "ollama_model": "some-model"},
        )
        assert response.status_code == 400

    def test_update_fallback_student_forbidden(self, regular_user, user_token):
        """Test student cannot update fallback settings"""
        response = client.put(
            "/api/settings/ai/fallback",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"provider": "ollama", "ollama_model": "llama3.2:latest"},
        )
        assert response.status_code == 403


class TestAISettingsAuthentication:
    """Test authentication requirements"""

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

    def test_get_fallback_settings_no_auth(self):
        """Test getting fallback settings without auth fails"""
        response = client.get("/api/settings/ai/fallback")
        assert response.status_code == 401

    def test_update_fallback_settings_no_auth(self):
        """Test updating fallback settings without auth fails"""
        response = client.put(
            "/api/settings/ai/fallback",
            json={"provider": "ollama", "ollama_model": "test"},
        )
        assert response.status_code == 401
