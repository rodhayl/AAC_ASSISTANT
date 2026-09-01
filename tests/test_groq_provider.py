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
