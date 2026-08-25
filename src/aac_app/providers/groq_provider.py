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
        # The parent class falls back to OPENROUTER_API_KEY; Groq uses its own
        # environment variable when no explicit key is passed.
        super().__init__(api_key=api_key or os.getenv("GROQ_API_KEY"), model=model)
        self.base_url = "https://api.groq.com/openai/v1"
        if not model:
            self.default_model = "openai/gpt-oss-20b"
            self._model = self.default_model

    def is_configured(self) -> bool:
        """Groq is configured when an API key is present."""
        return self.api_key is not None and len(self.api_key.strip()) > 0
