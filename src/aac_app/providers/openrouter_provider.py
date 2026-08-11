"""
OpenRouter Provider - Optional cloud LLM functionality
This provider is only used when users explicitly provide an OpenRouter API key
"""

import asyncio
import os
from typing import Any

import httpx
from loguru import logger

from .base_provider import BaseLLMProvider


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter API provider for optional cloud LLM functionality"""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        super().__init__()
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"
        # Keep the raw setting so singleton getters can distinguish an empty
        # configured value from the provider's resolved default model.
        self._configured_model = model or ""
        self.client = httpx.AsyncClient(timeout=30.0)
        self.sync_client = httpx.Client(timeout=5.0)
        self._pending_close_task: asyncio.Task | None = None
        self._close_started = False
        self.default_model = model or "meta-llama/llama-3.1-8b-instruct"
        self._model = self.default_model

    def get_default_model(self) -> str:
        """Get the default model for this provider"""
        return self.default_model

    def is_configured(self) -> bool:
        """Check if OpenRouter is properly configured"""
        return self.api_key is not None and len(self.api_key.strip()) > 0

    def is_available(self) -> bool:
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
        model: str | None = None,
        system: str | None = None,
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

    async def get_available_models(self) -> dict[str, Any]:
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

    def _consume_close_task(self, task: asyncio.Task) -> None:
        """Retrieve background close failures so they are never unhandled."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("OpenRouter async client close failed: {}", exc)

    async def close_async(self) -> None:
        """Close both HTTP transports while an event loop is running."""
        if self._close_started:
            pending = self._pending_close_task
            self._pending_close_task = None
            try:
                if pending is not None:
                    await pending
            except Exception as exc:
                logger.debug("OpenRouter async client close failed: {}", exc)
            finally:
                try:
                    self.sync_client.close()
                except Exception as exc:
                    logger.debug("OpenRouter sync client close failed: {}", exc)
            return

        self._close_started = True
        try:
            await self.client.aclose()
        finally:
            try:
                self.sync_client.close()
            except Exception as exc:
                logger.debug("OpenRouter sync client close failed: {}", exc)

    async def close(self):
        """Backward-compatible async close alias."""
        await self.close_async()

    def close_sync(self) -> None:
        """Close provider transports from synchronous cleanup paths."""
        if self._close_started:
            return
        self._close_started = True
        try:
            self.sync_client.close()
        except Exception as exc:
            logger.debug("OpenRouter sync client close failed: {}", exc)
        finally:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self.client.aclose())
            else:
                self._pending_close_task = loop.create_task(self.client.aclose())
                self._pending_close_task.add_done_callback(self._consume_close_task)
