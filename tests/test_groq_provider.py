from unittest.mock import AsyncMock, Mock

import pytest

from src.aac_app.providers.groq_provider import GroqProvider


@pytest.mark.anyio
async def test_groq_gpt_oss_uses_hidden_low_effort_reasoning(monkeypatch):
    provider = GroqProvider(api_key="gsk-test", model="openai/gpt-oss-120b")
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": "READY"}}],
    }
    post = AsyncMock(return_value=response)
    monkeypatch.setattr(provider.client, "post", post)

    assert await provider.generate("Reply READY", max_tokens=32) == "READY"
    payload = post.call_args.kwargs["json"]
    assert payload["reasoning_format"] == "hidden"
    assert payload["reasoning_effort"] == "low"
    await provider.close()


def test_groq_requires_an_explicit_model():
    """A listing-only client may be built from an API key alone."""
    provider = GroqProvider(api_key="gsk-test", model="")
    assert provider.is_configured() is True
    assert provider._configured_model == ""


@pytest.mark.anyio
async def test_groq_generate_requires_an_explicit_model():
    """Generation without an explicit model fails loudly, never defaults."""
    provider = GroqProvider(api_key="gsk-test", model="")
    with pytest.raises(ValueError, match="model must be configured explicitly"):
        await provider.generate("hello")
    await provider.close()


@pytest.mark.anyio
async def test_groq_rejects_empty_assistant_content(monkeypatch):
    provider = GroqProvider(api_key="gsk-test", model="openai/gpt-oss-120b")
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": "", "reasoning": "hidden"}}],
    }
    monkeypatch.setattr(provider.client, "post", AsyncMock(return_value=response))

    with pytest.raises(ValueError, match="empty assistant response"):
        await provider.generate("Reply READY", max_tokens=32)
    await provider.close()


def test_groq_generate_sync_uses_sync_client_and_enforces_model(monkeypatch):
    """The sync completion mirrors the async one: same payload through the
    sync client, and an explicit model is mandatory."""
    provider = GroqProvider(api_key="gsk-test", model="openai/gpt-oss-120b")
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": "nebulosa, agujero negro, quasar"}}],
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(provider.sync_client, "post", post)

    text = provider.generate_sync(
        "List topic words", max_tokens=150, temperature=0.5
    )
    assert text == "nebulosa, agujero negro, quasar"
    payload = post.call_args.kwargs["json"]
    assert payload["max_tokens"] == 150
    assert payload["temperature"] == 0.5
    assert payload["reasoning_format"] == "hidden"
    provider.close_sync()


def test_groq_generate_sync_requires_an_explicit_model():
    """Sync generation without a model fails loudly, never defaults."""
    provider = GroqProvider(api_key="gsk-test", model="")
    with pytest.raises(ValueError, match="model must be configured explicitly"):
        provider.generate_sync("hello")
    provider.close_sync()


@pytest.mark.anyio
async def test_groq_rate_limit_raises_provider_rate_limit_error(monkeypatch):
    """A 429 surfaces as ProviderRateLimitError so callers can retry with a
    short backoff instead of treating it like a broken configuration."""
    from src.aac_app.providers.base_provider import ProviderRateLimitError

    provider = GroqProvider(api_key="gsk-test", model="openai/gpt-oss-120b")
    response = Mock()
    response.status_code = 429
    response.text = "rate limit exceeded"
    monkeypatch.setattr(provider.client, "post", AsyncMock(return_value=response))

    with pytest.raises(ProviderRateLimitError, match="429"):
        await provider.generate("hello", max_tokens=32)
    await provider.close()


def test_groq_generate_sync_rate_limit_raises_provider_rate_limit_error(monkeypatch):
    """The sync path (used by symbol auto-generation) surfaces 429 the same
    way so the autogen service can apply its rate-limit cooldown."""
    from src.aac_app.providers.base_provider import ProviderRateLimitError

    provider = GroqProvider(api_key="gsk-test", model="openai/gpt-oss-120b")
    response = Mock()
    response.status_code = 429
    response.text = "rate limit exceeded"
    monkeypatch.setattr(provider.sync_client, "post", Mock(return_value=response))

    with pytest.raises(ProviderRateLimitError, match="429"):
        provider.generate_sync("hello", max_tokens=32)
    provider.close_sync()


class TestEffectiveGroqKey:
    """F10/D10: one credential precedence for every Groq caller.

    DB setting > canonical config (.env) > process environment, always
    stripped, and never falling back to another provider's key.
    """

    @staticmethod
    def _patch(monkeypatch, *, db_key: str = "", config_key: str = "", env_key: str | None = None):
        import src.api.deps.providers as providers

        monkeypatch.setattr(
            providers,
            "_get_setting_value",
            lambda key, default=None: db_key if key == "groq_api_key" else default,
        )
        monkeypatch.setattr(providers.config, "GROQ_API_KEY", config_key, raising=False)
        if env_key is None:
            monkeypatch.delenv("GROQ_API_KEY", raising=False)
        else:
            monkeypatch.setenv("GROQ_API_KEY", env_key)
        return providers

    def test_precedence_and_stripping(self, monkeypatch):
        providers = self._patch(
            monkeypatch, db_key="  gsk_db  ", config_key="gsk_cfg", env_key="gsk_env"
        )
        assert providers.resolve_groq_api_key() == "gsk_db"

        providers = self._patch(
            monkeypatch, db_key="", config_key="  gsk_cfg  ", env_key="gsk_env"
        )
        assert providers.resolve_groq_api_key() == "gsk_cfg"

        providers = self._patch(monkeypatch, db_key="", config_key="", env_key="  gsk_env  ")
        assert providers.resolve_groq_api_key() == "gsk_env"

    def test_never_falls_back_to_openrouter_key(self, monkeypatch):
        providers = self._patch(monkeypatch, db_key="", config_key="", env_key=None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-only-key")
        assert providers.resolve_groq_api_key() == ""
        provider = GroqProvider(api_key=None, model="openai/gpt-oss-120b")
        assert provider.api_key in (None, "")
        assert provider.is_configured() is False
        provider.close_sync()

    def test_parent_provider_still_resolves_its_own_env_key(self, monkeypatch):
        """D9: the shared ``_resolve_api_key`` hook must keep OpenRouter's own
        environment resolution intact, and must not adopt ``GROQ_API_KEY``."""
        from src.aac_app.providers.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENROUTER_API_KEY", "or-env-key")
        monkeypatch.setenv("GROQ_API_KEY", "gsk-other-provider")
        resolved = OpenRouterProvider(api_key=None, model="openrouter/free")
        assert resolved.api_key == "or-env-key"
        resolved.close_sync()

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        unresolved = OpenRouterProvider(api_key=None, model="openrouter/free")
        assert unresolved.api_key is None
        unresolved.close_sync()

        explicit = OpenRouterProvider(api_key="explicit-key")
        assert explicit.api_key == "explicit-key"
        explicit.close_sync()


class TestEffectiveGroqModel:
    """F10 completeness: the Groq model resolves with the same precedence as
    the key (DB > canonical config > process env), so the documented
    ``GROQ_MODEL`` setting actually takes effect in an env-only deployment
    instead of being silently ignored."""

    @staticmethod
    def _patch(
        monkeypatch, *, db_model: str = "", config_model: str = "", env_model: str | None = None
    ):
        import src.api.deps.providers as providers

        monkeypatch.setattr(
            providers,
            "_get_setting_value",
            lambda key, default=None: db_model if key == "groq_model" else default,
        )
        monkeypatch.setattr(providers.config, "GROQ_MODEL", config_model, raising=False)
        if env_model is None:
            monkeypatch.delenv("GROQ_MODEL", raising=False)
        else:
            monkeypatch.setenv("GROQ_MODEL", env_model)
        return providers

    def test_config_declares_the_setting_it_reads(self):
        """The documented ``GROQ_MODEL`` setting must exist in config; a
        monkeypatch with ``raising=False`` would otherwise hide its absence
        (the exact defect this class was added for)."""
        from src import config

        assert hasattr(config, "GROQ_MODEL")
        assert config.GROQ_MODEL == ""

    def test_precedence_and_stripping(self, monkeypatch):
        providers = self._patch(
            monkeypatch,
            db_model="  openai/db-model  ",
            config_model="openai/cfg-model",
            env_model="openai/env-model",
        )
        assert providers.resolve_groq_model() == "openai/db-model"

        providers = self._patch(
            monkeypatch, db_model="", config_model="  openai/cfg-model  ", env_model="openai/env-model"
        )
        assert providers.resolve_groq_model() == "openai/cfg-model"

        providers = self._patch(monkeypatch, db_model="", config_model="", env_model="  openai/env-model  ")
        assert providers.resolve_groq_model() == "openai/env-model"

    def test_env_only_deployment_is_configured(self, monkeypatch):
        """The production-gate shape: no persisted setting, model supplied by
        the environment. This must be honored, otherwise a fresh deployment
        can never become ready."""
        providers = self._patch(monkeypatch, env_model="openai/gpt-oss-120b")
        assert providers.resolve_groq_model() == "openai/gpt-oss-120b"

    def test_unconfigured_everywhere_stays_unconfigured(self, monkeypatch):
        """Fail closed is preserved: an empty resolution still reports "not
        configured" so warmup rejects it rather than guessing a model."""
        providers = self._patch(monkeypatch)
        assert providers.resolve_groq_model() == ""


class TestGroqProviderSingleton:
    """F10: unchanged configuration must not recreate (and close) the client
    other requests are using; a real change must."""

    def test_reuses_unchanged_configuration_and_recreates_on_change(self, monkeypatch):
        import src.api.deps.providers as providers

        monkeypatch.setattr(providers, "_groq_provider", None)
        settings = {"groq_model": "openai/gpt-oss-120b", "groq_api_key": "gsk_stable"}
        monkeypatch.setattr(
            providers, "_get_setting_value", lambda key, default=None: settings.get(key, default)
        )

        first = providers.get_groq_provider()
        assert providers.get_groq_provider() is first

        # A padded-but-equal DB key must not thrash the singleton (D10).
        settings["groq_api_key"] = "  gsk_stable  "
        assert providers.get_groq_provider() is first

        settings["groq_api_key"] = "gsk_changed"
        second = providers.get_groq_provider()
        assert second is not first
        assert second.api_key == "gsk_changed"

        # A model change also rebuilds; an unchanged one keeps the instance.
        settings["groq_model"] = "openai/gpt-oss-20b"
        third = providers.get_groq_provider()
        assert third is not second
        assert providers.get_groq_provider() is third
