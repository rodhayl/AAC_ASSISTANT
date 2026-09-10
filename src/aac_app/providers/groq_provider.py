"""
Groq Provider - Cloud LLM provider using Groq's OpenAI-compatible API.

Groq exposes an OpenAI-compatible chat completions API, so this provider
reuses the OpenRouterProvider implementation and only overrides the endpoint,
credential source, and default model.
"""

import os

from .openrouter_provider import OpenRouterProvider


class GroqProvider(OpenRouterProvider):
    """Groq API provider for optional cloud LLM functionality."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        # Never fall back to OPENROUTER_API_KEY; Groq uses only its own credential.
        resolved = api_key if api_key is not None else os.getenv("GROQ_API_KEY")
        # Bypass parent fallback: set directly without OPENROUTER lookup
        from .base_provider import BaseLLMProvider
        BaseLLMProvider.__init__(self)
        import httpx as _httpx
        self.api_key = resolved
        self.base_url = "https://api.groq.com/openai/v1"
        self._configured_model = model or ""
        self.client = _httpx.AsyncClient(timeout=30.0)
        self.sync_client = _httpx.Client(timeout=5.0)
        self.default_model = model or "meta-llama/llama-3.1-8b-instruct"
        self._model = self.default_model

    def is_configured(self) -> bool:
        """Groq is configured when an API key is present."""
        return self.api_key is not None and len(self.api_key.strip()) > 0

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        json_schema: dict | None = None,
        **kwargs,
    ) -> str:
        """Generate with Groq, requiring an explicitly configured model.

        The model requirement lives here instead of ``__init__`` so the
        model-listing endpoint (``/api/settings/ai/models/groq``) can build a
        client from an API key alone. Generation must never fall back to the
        parent's default model silently, so an empty configured model fails
        explicitly.
        """
        if not (model or self._configured_model):
            raise ValueError("Groq model must be configured explicitly")
        return await super().generate(
            prompt=prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=json_schema,
            **kwargs,
        )

    def generate_sync(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        json_schema: dict | None = None,
        **kwargs,
    ) -> str:
        """Synchronous Groq completion; same explicit-model rule as generate().

        The model requirement must never fall back to the parent's default
        model silently, so this mirrors the async contract exactly.
        """
        if not (model or self._configured_model):
            raise ValueError("Groq model must be configured explicitly")
        return super().generate_sync(
            prompt=prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=json_schema,
            **kwargs,
        )
