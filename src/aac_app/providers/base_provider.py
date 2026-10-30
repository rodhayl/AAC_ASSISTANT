"""
Base provider interface for LLM providers
Ensures consistent API across Ollama and OpenRouter
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(
        self,
    ):  # noqa: duplicate - intentional, each subclass has unique initialization
        self._model: Optional[str] = None

    @property
    def model(self) -> str:
        """Get the current model"""
        return self._model or self.get_default_model()

    def set_model(self, model: str):
        """Set the default model for generation"""
        self._model = model
        self.on_model_changed(model)

    @abstractmethod
    def get_default_model(
        self,
    ) -> str:  # noqa: duplicate - polymorphism, each provider has different default
        """Return the default model for this provider"""

    def on_model_changed(
        self, model: str
    ):  # noqa: duplicate - polymorphism, each provider has unique behavior
        """Hook called when model is changed (override in subclass)"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs
    ) -> str:
        """Generate text completion"""
