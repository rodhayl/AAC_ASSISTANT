"""
OpenRouter Provider - Optional cloud fallback for LLM functionality
This provider is only used when users explicitly provide an OpenRouter API key
"""

import os
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from .base_provider import BaseLLMProvider


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter API provider for optional cloud LLM functionality"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient(timeout=30.0)
        self.sync_client = httpx.Client(timeout=5.0)
        self.default_model = model or "meta-llama/llama-3.1-8b-instruct"
        self._model = self.default_model

    def get_default_model(self) -> str:
        """Get the default model for this provider"""
        return self.default_model

    def on_model_changed(self, model: str):
        """Update internal model when changed"""
        self.default_model = model
        logger.info(f"OpenRouter default model set to {model}")

    def is_configured(self) -> bool:
        """Check if OpenRouter is properly configured"""
        return self.api_key is not None and len(self.api_key.strip()) > 0

    def is_available(self) -> bool:  # noqa: duplicate
        if not self.is_configured():
            return False
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://aac-assistant.local",
                "X-Title": "AAC Assistant 2.0",
            }
            r = self.sync_client.get(
                f"{self.base_url}/models", headers=headers, timeout=2.0
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"OpenRouter not available: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs,
    ) -> str:
        """
        Generate text response - compatible interface with OllamaProvider.

        Args:
            prompt: User prompt
            model: Model to use (optional, uses default if not provided)
            system: System prompt (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Generated text
        """
        if not self.is_configured():
            raise ValueError("OpenRouter not configured. Please provide API key.")

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://aac-assistant.local",
                "X-Title": "AAC Assistant 2.0",
                "Content-Type": "application/json",
            }

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model or self.default_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            }

            response = await self.client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )

            if response.status_code != 200:
                logger.error(
                    f"OpenRouter API error: {response.status_code} - {response.text}"
                )
                raise Exception(f"OpenRouter API error: {response.status_code}")

            result = response.json()
            return result["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"OpenRouter generation failed: {e}")
            raise

    async def get_available_models(self) -> Dict[str, Any]:
        """Get list of available models from OpenRouter"""
        if not self.is_configured():
            return {}

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://aac-assistant.local",
                "X-Title": "AAC Assistant 2.0",
            }

            response = await self.client.get(f"{self.base_url}/models", headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get OpenRouter models: {response.status_code}")
                return {}

        except Exception as e:
            logger.error(f"Failed to get OpenRouter models: {e}")
            return {}

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
