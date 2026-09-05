"""Production provider-selection guarantees.

In ``ENVIRONMENT=production`` the app must never silently select a local
provider (Ollama / LM Studio / OpenRouter) as the primary LLM: Groq is the
only production LLM provider. These tests lock down:

1. ``get_llm_provider`` returns a GroqProvider in production regardless of
   the persisted ``ai_provider`` setting.
2. ``_init_llm_provider_sync`` builds the Groq client during warmup.
3. ``get_learning_service`` and ``get_board_generation_service`` refuse a
   non-Groq provider in production instead of degrading silently.
"""

from unittest.mock import Mock

import pytest

from src import config
from src.aac_app.providers.groq_provider import GroqProvider
from src.aac_app.providers.lmstudio_provider import LMStudioProvider
from src.aac_app.providers.ollama_provider import OllamaProvider
from src.api.deps import providers as providers_mod


class _Settings:
    """In-memory settings facade used instead of the DB-backed one."""

    def __init__(self, values: dict[str, str]):
        self._values = dict(values)

    def get_setting_value(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


@pytest.fixture
def production_env(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")


@pytest.fixture(autouse=True)
def _reset_providers():
    from src.api.deps import reset_providers

    reset_providers()
    yield
    reset_providers()


def _fake_settings(monkeypatch, values: dict[str, str]) -> None:
    settings = _Settings(values)
    monkeypatch.setattr(
        providers_mod.deps_package, "get_setting_value", settings.get_setting_value
    )


def test_get_llm_provider_forces_groq_in_production(monkeypatch, production_env):
    """Even when ai_provider=ollama is persisted, production uses Groq."""
    _fake_settings(
        monkeypatch,
        {
            "ai_provider": "ollama",  # stale/dev setting must be ignored
            "groq_api_key": "gsk-prod-key",
            "groq_model": "openai/gpt-oss-120b",
        },
    )

    provider = providers_mod.get_llm_provider()

    assert isinstance(provider, GroqProvider)
    assert provider.api_key == "gsk-prod-key"


def test_init_llm_provider_sync_builds_groq_in_production(monkeypatch, production_env):
    """Warmup constructs the Groq client, not Ollama, in production."""
    _fake_settings(
        monkeypatch,
        {
            "ai_provider": "lmstudio",  # stale/dev setting must be ignored
            "groq_api_key": "gsk-prod-key",
            "groq_model": "openai/gpt-oss-120b",
        },
    )

    ok = providers_mod._init_llm_provider_sync()

    assert ok is True
    groq = providers_mod._groq_provider
    assert isinstance(groq, GroqProvider)
    assert groq.api_key == "gsk-prod-key"


def test_learning_service_refuses_non_groq_in_production(monkeypatch, production_env):
    from src.api.deps import get_learning_service

    speech = Mock()
    llm = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

    with pytest.raises(
        RuntimeError, match="Production learning requires the configured Groq provider"
    ):
        get_learning_service(llm=llm, speech=speech)


def test_board_generation_refuses_non_groq_in_production(monkeypatch, production_env):
    from src.api.deps import get_board_generation_service

    llm = LMStudioProvider(base_url="http://localhost:1234/v1", model="gemma")

    with pytest.raises(
        RuntimeError,
        match="Production board generation requires the configured Groq provider",
    ):
        get_board_generation_service(llm=llm)


def test_learning_service_accepts_groq_in_production(monkeypatch, production_env):
    """A GroqProvider satisfies the production contract end-to-end."""
    from src.api.deps import get_learning_service

    speech = Mock()
    llm = GroqProvider(api_key="gsk-prod-key", model="openai/gpt-oss-120b")
    monkeypatch.setattr(
        providers_mod.deps_package, "get_setting_value", lambda key, default="": "1024"
    )

    service = get_learning_service(llm=llm, speech=speech)
    assert service.provider_type == "groq"


def test_non_production_allows_local_provider(monkeypatch):
    """Development may still use the persisted local provider."""
    from src.api.deps import get_learning_service

    _fake_settings(
        monkeypatch,
        {"ai_provider": "ollama", "ai_max_tokens": "512", "ai_temperature": "0.7"},
    )
    speech = Mock()
    llm = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

    service = get_learning_service(llm=llm, speech=speech)
    assert service.provider_type == "ollama"


def test_get_llm_provider_uses_persisted_provider_in_dev(monkeypatch):
    """In development, the persisted ai_provider choice is honored."""
    _fake_settings(
        monkeypatch,
        {
            "ai_provider": "lmstudio",
            "lmstudio_base_url": "http://localhost:1234/v1",
            "lmstudio_model": "gemma-4-12b-it-qat",
        },
    )

    provider = providers_mod.get_llm_provider()

    assert isinstance(provider, LMStudioProvider)
    assert provider.base_url == "http://localhost:1234/v1"
