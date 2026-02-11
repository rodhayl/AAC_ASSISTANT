import asyncio
import json
from typing import Callable, Dict, List, Optional

import httpx
from loguru import logger

from .base_provider import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """100% local LLM using Ollama"""

    # Hardware profiles for different system configurations
    HARDWARE_PROFILES = {
        "low_end": "qwen:1.8b-q4_0",  # 1.1GB, 4GB RAM
        "mid_range": "qwen:7b-q4_0",  # 4.4GB, 8GB RAM (RECOMMENDED)
        "high_end": "qwen:14b-q4_0",  # 8.5GB, 16GB RAM
        "server": "llama3:70b-q4_0",  # 40GB, 64GB RAM
    }

    def __init__(
        self,
        base_url="http://localhost:11434",
        hardware_profile="mid_range",
        model: Optional[str] = None,
    ):
        super().__init__()
        self.base_url = base_url
        self.hardware_profile = hardware_profile
        # Default to user-specified model, env var, or hardware profile
        env_model = None
        try:
            import os

            env_model = os.getenv("OLLAMA_MODEL")
        except Exception:
            env_model = None
        self.recommended_model = (
            model or env_model or self.HARDWARE_PROFILES[hardware_profile]
        )
        self._model = self.recommended_model
        # Allow longer generations; keep connect timeout short
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=5.0, read=120.0)
        )
        self.sync_client = httpx.Client(
            timeout=httpx.Timeout(120.0, connect=5.0, read=120.0)
        )
        logger.info(
            f"Ollama provider initialized with profile={hardware_profile}, model={self.recommended_model}"
        )

    def get_default_model(self) -> str:
        """Get the default model for this provider"""
        return self.recommended_model

    def on_model_changed(self, model: str):
        """Update internal model when changed"""
        self.recommended_model = model
        logger.info(f"Ollama default model set to {model}")

    async def generate(
        self,
        prompt: str,
        model: str = None,
        system: str = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        json_schema: dict = None,
        **kwargs,
    ) -> str:
        """Generate text completion

        Args:
            prompt: User prompt
            model: Model name
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            json_schema: Optional JSON schema for structured output
            **kwargs: Additional options
        """

        if not model:
            model = self.recommended_model

        # Log the exact model being used for observability
        logger.info(f"Ollama generating with model: '{model}' (System: {bool(system)}, JSON: {bool(json_schema)})")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            logger.debug(f"Generating with model {model}, prompt: {prompt[:50]}...")

            request_data = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    **kwargs,
                },
            }

            # Enable JSON mode if schema provided
            if json_schema:
                request_data["format"] = "json"
                # Ollama expects the schema in the prompt or system message
                # We'll add it to the system message
                schema_instruction = f"\n\nRespond with valid JSON matching this schema: {json.dumps(json_schema)}"
                if messages[0]["role"] == "system":
                    messages[0]["content"] += schema_instruction
                else:
                    messages.insert(
                        0, {"role": "system", "content": schema_instruction}
                    )

            response = await self.client.post(
                f"{self.base_url}/api/chat", json=request_data
            )

            response.raise_for_status()
            result = response.json()

            generated_text = result["message"]["content"]
            logger.debug(f"Generated text: {generated_text[:50]}...")
            return generated_text

        except httpx.TimeoutException as e:
            logger.error(f"Ollama timeout: {e}")
            raise ConnectionError(
                f"Ollama timed out at {self.base_url}. Try again or reduce request size."
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Ollama HTTP error {e.response.status_code}: {e.response.text}"
            )
            if e.response.status_code == 404:
                raise ConnectionError(
                    f"Ollama API endpoint not found. Ensure Ollama is running "
                    f"and model '{model}' is available. "
                    f"Run 'ollama pull {model}'."
                )
            else:
                raise ConnectionError(
                    f"Ollama returned error {e.response.status_code}: {e.response.text}"
                )
        except httpx.RequestError as e:
            logger.error(f"Ollama request failed: {e}")
            raise ConnectionError(
                f"Failed to connect to Ollama at {self.base_url}. Make sure Ollama is running and reachable."
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ollama response: {e}")
            raise ValueError("Invalid response from Ollama")
        except KeyError as e:
            logger.error(f"Unexpected response format from Ollama: {e}")
            raise ValueError("Unexpected response format from Ollama")

    async def generate_streaming(
        self,
        prompt: str,
        callback: Callable[[str], None],
        model: str = None,
        system: str = None,
        **kwargs,
    ):
        """Stream generated text"""

        if not model:
            model = self.recommended_model

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            logger.debug(f"Streaming generation with model {model}")

            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": True},
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                callback(data["message"]["content"])
                        except json.JSONDecodeError:
                            logger.warning(
                                f"Failed to parse streaming response line: {line}"
                            )

        except httpx.RequestError as e:
            logger.error(f"Ollama streaming request failed: {e}")
            raise ConnectionError(f"Failed to connect to Ollama at {self.base_url}")

    def generate_sync(
        self,
        prompt: str,
        model: str = None,
        system: str = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs,
    ) -> str:
        """Synchronous text generation (for non-async contexts)"""

        if not model:
            model = self.recommended_model

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            logger.debug(f"Sync generation with model {model}")

            response = self.sync_client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        **kwargs,
                    },
                },
            )

            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]

        except httpx.TimeoutException as e:
            logger.error(f"Ollama sync timeout: {e}")
            raise ConnectionError(f"Ollama timed out at {self.base_url}.")
        except httpx.RequestError as e:
            logger.error(f"Ollama sync request failed: {e}")
            raise ConnectionError(f"Failed to connect to Ollama at {self.base_url}")

    def list_models(self) -> List[str]:
        """List installed Ollama models"""
        try:
            logger.debug("Listing Ollama models")
            response = self.sync_client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()

            models_data = response.json()
            models = [m["name"] for m in models_data.get("models", [])]
            logger.info(f"Found {len(models)} models: {models}")
            return models

        except httpx.RequestError as e:
            logger.error(f"Failed to list models: {e}")
            return []

    def is_available(self) -> bool:  # noqa: duplicate
        """Check if Ollama is running"""
        try:
            logger.debug("Checking Ollama availability")
            response = self.sync_client.get(f"{self.base_url}/api/tags", timeout=2.0)
            available = response.status_code == 200
            logger.info(f"Ollama availability: {available}")
            return available

        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            return False

    def get_model_info(self, model: str) -> Optional[Dict]:
        """Get information about a specific model"""
        try:
            response = self.sync_client.get(
                f"{self.base_url}/api/show", params={"name": model}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get model info for {model}: {e}")
            return None

    def close(self):
        """Close HTTP clients"""
        try:
            self.sync_client.close()
            try:
                # Try to close async client if we're in an async context
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.client.aclose())
            except Exception:
                # If no loop or other error, just let it be
                pass
        except Exception as e:
            logger.error(f"Error closing Ollama provider: {e}")
