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
