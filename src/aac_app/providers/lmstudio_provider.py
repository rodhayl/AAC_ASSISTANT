"""
LM Studio Provider - Local LLM provider using OpenAI-compatible API
"""

from typing import Any, Dict, Optional

from loguru import logger

from .openrouter_provider import OpenRouterProvider


class LMStudioProvider(OpenRouterProvider):
    """
    LM Studio provider connecting to local instance via OpenAI-compatible API.
    Defaults to http://localhost:1234/v1
    """

    def __init__(self, base_url: str = "http://localhost:1234/v1", model: Optional[str] = None):
        # Initialize parent with dummy key since LM Studio doesn't strictly need one
        # but the parent class checks for it.
        super().__init__(api_key="lm-studio", model=model)
        self.base_url = base_url.rstrip("/")
        # Override default model if not provided
        if not model:
            self.default_model = "local-model"  # Placeholder, usually user selects one
            self._model = self.default_model
        
        logger.info(f"LM Studio provider initialized with url={self.base_url}")

    def is_configured(self) -> bool:
        """LM Studio is considered configured if we have a base URL (which has a default)"""
        return bool(self.base_url)

    async def get_available_models(self) -> Dict[str, Any]:
        """Get available models from LM Studio"""
        # Parent class implementation works, but we might want to handle errors differently
        # or parse the response if LM Studio format differs slightly (usually identical)
        try:
            return await super().get_available_models()
        except Exception as e:
            logger.error(f"LM Studio get_models failed: {e}")
            return {"data": []}

    def on_model_changed(self, model: str):
        """Update internal model when changed"""
        self.default_model = model
        logger.info(f"LM Studio default model set to {model}")
