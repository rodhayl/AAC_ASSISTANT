"""
Base provider interface for LLM providers
Ensures consistent API across Ollama and OpenRouter
"""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(
        self,
    ):
        self._model: str | None = None

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
    ) -> str:
        """Return the default model for this provider"""

    def on_model_changed(
        self, model: str
    ):
        """Hook called when model is changed (override in subclass)"""

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
