"""Composed public learning companion service implementation."""

from collections.abc import Iterator

from loguru import logger
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import UserSettings
from ...providers.local_speech_provider import LocalSpeechProvider
from ...providers.local_tts_provider import LocalTTSProvider
from ...providers.ollama_provider import OllamaProvider
from ...providers.openrouter_provider import OpenRouterProvider
from ...services.aac_expander_service import AACExpanderService
from ...services.guardian_profile_service import get_guardian_profile_service
from ...services.symbol_analytics import SymbolAnalytics
from ...services.symbol_semantics import SymbolSemantics
from .common import AAC_SYSTEM_PROMPT, AACPromptProfile
from .questions import QuestionGenerationMixin
from .responses import ResponseProcessingMixin
from .session import SessionLifecycleMixin
from .summaries import SessionSummaryMixin


class LearningCompanionService(
    SessionLifecycleMixin,
    QuestionGenerationMixin,
    ResponseProcessingMixin,
    SessionSummaryMixin,
):
    def __init__(
        self,
        llm_provider: OllamaProvider | OpenRouterProvider,
        speech_provider: LocalSpeechProvider,
        tts_provider: LocalTTSProvider,
        default_max_tokens: int = 1024,
        default_temperature: float = 0.5,
    ):
        self.llm = llm_provider
        self.speech = speech_provider
        self.tts = tts_provider

        # LLM behavior defaults (can be overridden via AppSettings)
        self.default_max_tokens = max(64, int(default_max_tokens or 1024))
        # Clamp temperature to reasonable range
        self.default_temperature = float(
            default_temperature if default_temperature is not None else 0.5
        )
        if self.default_temperature < 0.0:
            self.default_temperature = 0.0
        if self.default_temperature > 1.5:
            self.default_temperature = 1.5

        # Determine provider type
        self.provider_type = (
            "openrouter" if isinstance(llm_provider, OpenRouterProvider) else "ollama"
        )

        # Initialize symbol semantics analyzer and expander
        self.symbol_semantics = SymbolSemantics()
        self.aac_expander = AACExpanderService()
        self.aac_prompt_profile = AACPromptProfile()
        self.symbol_analytics = SymbolAnalytics()

        # Guardian profile service for personalized prompts
        self.guardian_profile_service = get_guardian_profile_service()

        logger.info(
            f"Learning Companion Service initialized with {self.provider_type} provider "
            f"(max_tokens={self.default_max_tokens}, temperature={self.default_temperature})"
        )

    def _session_scope(self, db: Session | None) -> Iterator[Session]:
        """Use a request session when supplied, otherwise open a background session."""
        if db is not None:
            yield db
            return
        with get_session() as session:
            yield session

    def _get_system_prompt(self, user_id: int, db: Session | None = None) -> str:
        """
        Get the personalized system prompt for a user.

        If the user has a guardian profile configured by a teacher/admin,
        use that. Otherwise, fall back to the default AAC system prompt.

        Args:
            user_id: The user's ID

        Returns:
            Personalized system prompt string
        """
        try:
            # Try to get personalized prompt from guardian profile
            prompt = self.guardian_profile_service.build_system_prompt(user_id, db=db)
            if prompt and len(prompt) > 50:  # Ensure we got a real prompt
                logger.debug(f"Using personalized prompt for user {user_id}")
                return prompt
        except Exception as e:
            logger.warning(f"Failed to get guardian profile prompt for user {user_id}: {e}")

        # Fall back to default prompt
        logger.debug(f"Using default AAC prompt for user {user_id}")
        return AAC_SYSTEM_PROMPT

    def _get_user_language(self, user_id: int, db: Session | None = None) -> str:
        try:
            with self._session_scope(db) as session:
                settings = (
                    session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
                )
                if settings and settings.ui_language:
                    return settings.ui_language
        except Exception:
            pass
        return "es"
