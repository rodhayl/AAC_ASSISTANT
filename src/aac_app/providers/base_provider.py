"""
Base provider interface for LLM providers
Ensures consistent API across Ollama and OpenRouter
"""

import asyncio
from abc import ABC, abstractmethod

from loguru import logger


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(
        self,
    ):
        self._model: str | None = None
        # HTTP transports are owned by concrete providers. The shared close
        # machinery below tolerates either transport being absent.
        self.client = None
        self.sync_client = None
        self._pending_close_task: asyncio.Task | None = None
        self._close_started = False

    @property
    def model(self) -> str:
        """Get the current model"""
        return self._model or self.get_default_model()

    @abstractmethod
    def get_default_model(
        self,
    ) -> str:
        """Return the default model for this provider"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs
    ) -> str:
        """Generate text completion"""

    def _close_sync_transport(self) -> None:
        """Close the synchronous transport, tolerating provider errors."""
        if self.sync_client is None:
            return
        try:
            self.sync_client.close()
        except Exception as exc:
            logger.debug("{} sync client close failed: {}", type(self).__name__, exc)

    def _consume_close_task(self, task: asyncio.Task) -> None:
        """Retrieve background close failures so they are never unhandled."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("{} async client close failed: {}", type(self).__name__, exc)

    async def close_async(self) -> None:
        """Close both HTTP transports while an event loop is running."""
        if self.client is None and self.sync_client is None:
            return
        if self._close_started:
            pending = self._pending_close_task
            self._pending_close_task = None
            try:
                if pending is not None:
                    await pending
            except Exception as exc:
                logger.debug("{} async client close failed: {}", type(self).__name__, exc)
            finally:
                self._close_sync_transport()
            return

        self._close_started = True
        try:
            if self.client is not None:
                await self.client.aclose()
        finally:
            self._close_sync_transport()

    def close_sync(self) -> None:
        """Close HTTP clients from synchronous cleanup paths."""
        if self.client is None and self.sync_client is None:
            return
        if self._close_started:
            return
        self._close_started = True
        try:
            self._close_sync_transport()
        finally:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                if self.client is not None:
                    asyncio.run(self.client.aclose())
            else:
                if self.client is not None:
                    self._pending_close_task = loop.create_task(self.client.aclose())
                    self._pending_close_task.add_done_callback(self._consume_close_task)
