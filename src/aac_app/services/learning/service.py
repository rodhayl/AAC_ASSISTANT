"""Composed public learning companion service implementation."""


from loguru import logger
from sqlalchemy.orm import Session

from ...db import session_scope
from ...models import UserSettings
from ...providers.lmstudio_provider import LMStudioProvider
from ...providers.local_speech_provider import LocalSpeechProvider
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
        default_max_tokens: int = 1024,
        default_temperature: float = 0.5,
    ):
        self.llm = llm_provider
        self.speech = speech_provider

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

        # Determine provider type. LM Studio must be checked first: its provider
        # subclasses OpenRouterProvider (OpenAI-compatible API), so an isinstance
        # check against OpenRouter alone would mislabel LM Studio sessions.
        if isinstance(llm_provider, LMStudioProvider):
            self.provider_type = "lmstudio"
        elif isinstance(llm_provider, OpenRouterProvider):
            self.provider_type = "openrouter"
        else:
            self.provider_type = "ollama"

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

    _session_scope = staticmethod(session_scope)

    def _get_system_prompt(
        self,
        user_id: int,
        db: Session | None = None,
        mode_key: str | None = None,
        mode_instruction: str | None = None,
    ) -> str:
        """
        Get the personalized system prompt for a user.

        If the user has a guardian profile configured by a teacher/admin,
        use that. Otherwise, fall back to the default AAC system prompt.
        When a Learning Mode is active for the session, its
        ``prompt_instruction`` is appended so custom modes actually shape
        the companion's behavior.

        Args:
            user_id: The user's ID
            mode_key: Optional Learning Mode key whose prompt_instruction
                should be appended to the base prompt.
            mode_instruction: Optional raw instruction to append. When given
                it takes precedence over a ``mode_key`` lookup (used when
                previewing a mode that has not been saved yet).

        Returns:
            Personalized system prompt string
        """
        prompt = AAC_SYSTEM_PROMPT
        try:
            # Try to get personalized prompt from guardian profile
            guardian_prompt = self.guardian_profile_service.build_system_prompt(
                user_id, db=db
            )
            if guardian_prompt and len(guardian_prompt) > 50:
                logger.debug(f"Using personalized prompt for user {user_id}")
                prompt = guardian_prompt
        except Exception as e:
            logger.warning(
                f"Failed to get guardian profile prompt for user {user_id}: {e}"
            )
            logger.debug(f"Using default AAC prompt for user {user_id}")

        # Append the active Learning Mode's instructions (custom system prompt)
        if mode_key and mode_instruction is None:
            mode_instruction = self._get_mode_instruction(mode_key, db=db)
        if mode_instruction and mode_instruction.strip():
            logger.debug(f"Appending mode instruction for user {user_id}")
            prompt = f"{prompt}\n\n{mode_instruction.strip()}".strip()

        return prompt

    def preview_system_prompt(
        self,
        user_id: int,
        mode_key: str | None = None,
        mode_instruction: str | None = None,
        db: Session | None = None,
    ) -> str:
        """
        Return the exact system prompt a session would send for this user.

        Used by the teacher/admin preview in Settings -> Learning Modes so the
        assembled prompt (guardian profile + mode instruction) can be inspected
        before the mode is saved or a session is started.
        """
        return self._get_system_prompt(
            user_id,
            db=db,
            mode_key=mode_key,
            mode_instruction=mode_instruction,
        )

    def build_conversation_user_prompt(
        self,
        student_message: str,
        topic: str = "general conversation",
        context: str = "",
        lang: str = "es",
    ) -> str:
        """
        Build the exact user prompt the conversational LLM path sends.

        Mirrors the non-symbol conversational template in ``responses.py`` so
        the Settings preview can show exactly what the LLM receives for a
        student's question without drifting from the real code path.
        """
        lang_instruction = (
            "Respond in Spanish." if lang.startswith("es") else "Respond in English."
        )
        return (
            "Previous conversation:\n"
            f"    {context}\n"
            "\n"
            f"    Student's latest message: {student_message}\n"
            "\n"
            f"    Topic: {topic}\n"
            "\n"
            f"    Write a helpful response to the student (1-2 friendly sentences). "
            f"Ask a question or share a fact about {topic}. {lang_instruction}"
        )

    def _get_mode_instruction(
        self, mode_key: str, db: Session | None = None
    ) -> str | None:
        """Look up a Learning Mode's prompt_instruction by its key."""
        try:
            with self._session_scope(db) as session:
                from ...models import LearningMode

                mode = (
                    session.query(LearningMode)
                    .filter(LearningMode.key == mode_key)
                    .first()
                )
                if mode and mode.prompt_instruction:
                    return mode.prompt_instruction.strip()
        except Exception as e:
            logger.warning(f"Failed to look up learning mode '{mode_key}': {e}")
        return None

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
