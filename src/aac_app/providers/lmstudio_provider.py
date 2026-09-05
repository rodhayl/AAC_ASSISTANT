"""
LM Studio Provider - Local LLM provider using OpenAI-compatible API
"""

from loguru import logger

from src import config

from .openrouter_provider import OpenRouterProvider


class LMStudioProvider(OpenRouterProvider):
    """
    LM Studio provider connecting to local instance via OpenAI-compatible API.
    Uses the configured LM Studio base URL, with the application default from config.
    """

    def __init__(self, base_url: str | None = None, model: str | None = None):
        # Initialize parent with dummy key since LM Studio doesn't strictly need one
        # but the parent class checks for it.
        super().__init__(api_key="lm-studio", model=model)
        self.base_url = (base_url or config.LMSTUDIO_BASE_URL).rstrip("/")
        # Override default model if not provided
        if not model:
            self.default_model = "local-model"  # Placeholder, usually user selects one
            self._model = self.default_model

        logger.info(f"LM Studio provider initialized with url={self.base_url}")

    def is_configured(self) -> bool:
        """LM Studio is considered configured if we have a base URL (which has a default)"""
        return bool(self.base_url)
