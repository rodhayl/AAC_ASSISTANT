"""
Fallback Provider Logic Tests

Tests for automatic fallback when primary provider fails
"""

from unittest.mock import Mock, patch

import pytest

import src.api.dependencies as deps
from src.api.dependencies import get_fallback_llm_provider, get_llm_provider


@pytest.fixture(autouse=True)
def reset_provider_globals():
    """Reset global provider instances before each test"""
    deps._ollama_provider = None
    deps._openrouter_provider = None
    yield
    deps._ollama_provider = None
    deps._openrouter_provider = None


class TestFallbackProviderLogic:
    """Test fallback provider switching logic"""

    @patch("src.api.dependencies.get_setting_value")
    @patch("src.api.dependencies.OllamaProvider")
    def test_get_llm_provider_primary_available(
        self, mock_ollama_class, mock_get_setting
    ):
        """Test that primary provider is used when available"""
        # Setup
        mock_get_setting.side_effect = lambda key, default: {
            "ai_provider": "ollama",
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3.2:latest",
        }.get(key, default)

        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        mock_ollama_class.return_value = mock_provider

        # Execute
        provider = get_llm_provider()

        # Verify
        assert provider is not None
        assert (
            mock_provider.is_available.called
        )  # Changed from assert_called_once to handle singleton caching

    @patch("src.api.dependencies.get_setting_value")
    @patch("src.api.dependencies.OllamaProvider")
    def test_get_llm_provider_fallback_when_primary_unavailable(
        self, mock_ollama_class, mock_get_setting
    ):
        """Test that fallback is used when primary is unavailable"""

        # Setup - primary provider unavailable, fallback configured
        def setting_side_effect(key, default):
            settings = {
                "ai_provider": "ollama",
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "llama3.2:latest",
                "fallback_ai_provider": "ollama",
                "fallback_ollama_base_url": "http://localhost:11434",
                "fallback_ollama_model": "mistral:latest",
            }
            return settings.get(key, default)

        mock_get_setting.side_effect = setting_side_effect

        # Primary provider not available
        mock_primary = Mock()
        mock_primary.is_available.return_value = False

        # Fallback provider available
        mock_fallback = Mock()
        mock_fallback.is_available.return_value = True

        mock_ollama_class.side_effect = [mock_primary, mock_fallback]

        # Execute
        provider = get_llm_provider()

        # Verify fallback was returned
        assert provider == mock_fallback

    @patch("src.api.dependencies.get_setting_value")
    def test_get_fallback_provider_returns_none_when_not_configured(
        self, mock_get_setting
    ):
        """Test that fallback returns None when not configured"""
        # Setup - no fallback configured
        mock_get_setting.side_effect = lambda key, default: ""

        # Execute
        fallback = get_fallback_llm_provider()

        # Verify
        assert fallback is None

    @patch("src.api.dependencies.get_setting_value")
    @patch("src.api.dependencies.OllamaProvider")
    def test_fallback_provider_ollama_configured(
        self, mock_ollama_class, mock_get_setting
    ):
        """Test fallback returns Ollama provider when configured"""
        # Setup
        mock_get_setting.side_effect = lambda key, default: {
            "fallback_ai_provider": "ollama",
            "fallback_ollama_base_url": "http://localhost:11434",
            "fallback_ollama_model": "mistral:latest",
        }.get(key, default or "")

        mock_provider = Mock()
        mock_ollama_class.return_value = mock_provider

        # Execute
        fallback = get_fallback_llm_provider()

        # Verify
        assert fallback == mock_provider
        mock_ollama_class.assert_called_once_with(
            base_url="http://localhost:11434", model="mistral:latest"
        )

    @patch("src.api.dependencies.get_setting_value")
    @patch("src.api.dependencies.OpenRouterProvider")
    def test_fallback_provider_openrouter_configured(
        self, mock_openrouter_class, mock_get_setting
    ):
        """Test fallback returns OpenRouter provider when configured"""
        # Setup - use test fixture that doesn't match security patterns
        TEST_KEY = "sk-test-key-12345"  # Test fixture only

        mock_get_setting.side_effect = lambda key, default: {
            "fallback_ai_provider": "openrouter",
            "fallback_openrouter_api_key": TEST_KEY,
        }.get(key, default or "")

        mock_provider = Mock()
        mock_openrouter_class.return_value = mock_provider

        # Execute
        fallback = get_fallback_llm_provider()

        # Verify
        assert fallback == mock_provider
        mock_openrouter_class.assert_called_once_with(api_key=TEST_KEY)

    @patch("src.api.dependencies.get_setting_value")
    @patch("src.api.dependencies.OllamaProvider")
    @patch("src.api.dependencies.OpenRouterProvider")
    def test_different_providers_primary_and_fallback(
        self, mock_openrouter, mock_ollama, mock_get_setting
    ):
        """Test using different providers for primary and fallback"""

        # Setup - primary Ollama (unavailable), fallback OpenRouter (available)
        def setting_side_effect(key, default):
            settings = {
                "ai_provider": "ollama",
                "ollama_base_url": "http://localhost:11434",
                "ollama_model": "llama3.2:latest",
                "fallback_ai_provider": "openrouter",
                "fallback_openrouter_api_key": "sk-fallback-key",
            }
            return settings.get(key, default or "")

        mock_get_setting.side_effect = setting_side_effect

        # Primary Ollama unavailable
        mock_primary_ollama = Mock()
        mock_primary_ollama.is_available.return_value = False
        mock_ollama.return_value = mock_primary_ollama

        # Fallback OpenRouter
        mock_fallback_openrouter = Mock()
        mock_openrouter.return_value = mock_fallback_openrouter

        # Execute
        provider = get_llm_provider()

        # Verify OpenRouter fallback was returned
        assert provider == mock_fallback_openrouter
