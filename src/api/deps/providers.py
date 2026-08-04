"""Lazy provider singletons and startup warmup orchestration."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from fastapi import Depends
from loguru import logger

from src import config
from src.aac_app.providers.lmstudio_provider import LMStudioProvider
from src.aac_app.providers.local_speech_provider import LocalSpeechProvider
from src.aac_app.providers.ollama_provider import OllamaProvider
from src.aac_app.providers.openrouter_provider import OpenRouterProvider
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.board_generation_service import BoardGenerationService
from src.aac_app.services.learning_companion_service import LearningCompanionService
from src.aac_app.services.local_vector_store import LocalVectorStore
from src.api import deps as deps_package

_ollama_provider: OllamaProvider | None = None
_openrouter_provider: OpenRouterProvider | None = None
_lmstudio_provider: LMStudioProvider | None = None
_speech_provider: LocalSpeechProvider | None = None
_achievement_system: AchievementSystem | None = None
_vector_store: LocalVectorStore | None = None

_startup_state: dict[str, Any] = {
    "initialized": False,
    "initializing": False,
    "providers_ready": {
        "speech": False,
        "llm": False,
        "achievement": False,
        "vector_store": False,
    },
    "errors": [],
    "startup_time_ms": 0,
}
_startup_lock = threading.Lock()


def _get_setting_value(key: str, default: str = "") -> str:
    """Resolve through the package facade so tests and callers can override it."""
    return deps_package.get_setting_value(key, default)


def get_ollama_provider() -> OllamaProvider:
    """Return the configured Ollama provider singleton."""
    global _ollama_provider

    base_url = _get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL)
    model = _get_setting_value("ollama_model", "")

    if _ollama_provider is None:
        logger.info(
            f"Initializing global OllamaProvider with base_url={base_url}, model={model}"
        )
        _ollama_provider = OllamaProvider(base_url=base_url, model=model)
    elif (
        _ollama_provider.base_url != base_url
        or _ollama_provider.recommended_model != model
    ):
        logger.info(
            "Ollama settings changed. Re-initializing provider. "
            f"(URL: {_ollama_provider.base_url}->{base_url}, "
            f"Model: {_ollama_provider.recommended_model}->{model})"
        )
        _ollama_provider = OllamaProvider(base_url=base_url, model=model)

    return _ollama_provider


def get_openrouter_provider() -> OpenRouterProvider:
    """Return the configured OpenRouter provider singleton."""
    global _openrouter_provider

    api_key = _get_setting_value("openrouter_api_key", "")
    model = _get_setting_value("openrouter_model", "")

    if _openrouter_provider is None:
        logger.info("Initializing global OpenRouterProvider")
        _openrouter_provider = OpenRouterProvider(api_key=api_key, model=model)
    elif (
        _openrouter_provider.api_key != api_key
        or _openrouter_provider.default_model != model
    ):
        logger.info("OpenRouter settings changed. Re-initializing provider.")
        _openrouter_provider = OpenRouterProvider(api_key=api_key, model=model)

    return _openrouter_provider


def get_lmstudio_provider() -> LMStudioProvider:
    """Return the configured LM Studio provider singleton."""
    global _lmstudio_provider

    base_url = _get_setting_value("lmstudio_base_url", "http://localhost:1234/v1")
    model = _get_setting_value("lmstudio_model", "")

    if _lmstudio_provider is None:
        logger.info("Initializing global LMStudioProvider")
        _lmstudio_provider = LMStudioProvider(base_url=base_url, model=model)
    else:
        current_url = _lmstudio_provider.base_url.rstrip("/")
        new_url = base_url.rstrip("/")
        if current_url != new_url or _lmstudio_provider.default_model != model:
            logger.info(
                f"LM Studio settings changed. Re-initializing provider. "
                f"(URL: {current_url}->{new_url})"
            )
            _lmstudio_provider = LMStudioProvider(base_url=base_url, model=model)

    return _lmstudio_provider


def get_llm_provider() -> OllamaProvider | OpenRouterProvider | LMStudioProvider:
    """Return the configured primary LLM provider."""
    provider_type = _get_setting_value("ai_provider", "ollama")

    if provider_type == "openrouter":
        provider = get_openrouter_provider()
    elif provider_type == "lmstudio":
        provider = get_lmstudio_provider()
    else:
        provider = get_ollama_provider()

    return provider


def get_speech_provider() -> LocalSpeechProvider:
    """Return the local speech provider singleton."""
    global _speech_provider
    if _speech_provider is None:
        logger.info("Initializing global LocalSpeechProvider")
        _speech_provider = LocalSpeechProvider()
    return _speech_provider


def get_achievement_system() -> AchievementSystem:
    """Return the achievement system singleton."""
    global _achievement_system
    if _achievement_system is None:
        logger.info("Initializing global AchievementSystem")
        _achievement_system = AchievementSystem()
    return _achievement_system


def get_vector_store() -> LocalVectorStore:
    """Return the local vector store singleton."""
    global _vector_store
    if _vector_store is None:
        logger.info("Initializing global LocalVectorStore")
        _vector_store = LocalVectorStore()
    return _vector_store


def _get_llm_settings() -> tuple[int, float]:
    """Read the configured primary LLM behavior settings."""
    try:
        max_tokens = int(_get_setting_value("ai_max_tokens", "1024"))
    except ValueError:
        max_tokens = 1024

    try:
        temperature = float(_get_setting_value("ai_temperature", "0.5"))
    except ValueError:
        temperature = 0.5

    return max_tokens, temperature


def get_learning_service(
    llm: OllamaProvider | OpenRouterProvider | LMStudioProvider = Depends(
        get_llm_provider
    ),
    speech: LocalSpeechProvider = Depends(get_speech_provider),
) -> LearningCompanionService:
    """Build a learning service with the configured provider defaults."""
    max_tokens, temperature = _get_llm_settings()
    return LearningCompanionService(
        llm,
        speech,
        default_max_tokens=max_tokens,
        default_temperature=temperature,
    )


def get_board_generation_service(
    llm: OllamaProvider | OpenRouterProvider | LMStudioProvider = Depends(
        get_llm_provider
    ),
) -> BoardGenerationService:
    """Build a board-generation service with the configured LLM."""
    return BoardGenerationService(llm)


def _init_speech_provider_sync() -> bool:
    """Initialize speech provider without loading its model."""
    global _speech_provider
    try:
        start = time.time()
        logger.info("Warmup: Initializing speech recognition provider (lazy mode)...")
        _speech_provider = LocalSpeechProvider(lazy_load=True)
        elapsed = (time.time() - start) * 1000
        if _speech_provider.is_available():
            logger.info(
                f"Warmup: Speech provider initialized in {elapsed:.0f}ms "
                "(model will load on first use)"
            )
        else:
            logger.warning(
                "Warmup: Speech provider initialized but Whisper is not installed"
            )
        return True
    except Exception as exc:
        logger.error(f"Warmup: Failed to initialize speech provider: {exc}")
        return False


def _init_llm_provider_sync() -> bool:
    """Initialize the configured LLM client without making a network call."""
    global _ollama_provider, _openrouter_provider, _lmstudio_provider
    try:
        start = time.time()
        provider_type = _get_setting_value("ai_provider", "ollama")
        logger.info(f"Warmup: Initializing {provider_type} LLM provider...")

        if provider_type == "openrouter":
            _openrouter_provider = OpenRouterProvider(
                api_key=_get_setting_value("openrouter_api_key", "")
            )
        elif provider_type == "lmstudio":
            _lmstudio_provider = LMStudioProvider(
                base_url=_get_setting_value(
                    "lmstudio_base_url", "http://localhost:1234/v1"
                ),
                model=_get_setting_value("lmstudio_model", ""),
            )
        else:
            _ollama_provider = OllamaProvider(
                base_url=_get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL),
                model=_get_setting_value("ollama_model", ""),
            )

        elapsed = (time.time() - start) * 1000
        logger.info(f"Warmup: LLM provider ({provider_type}) ready in {elapsed:.0f}ms")
        return True
    except Exception as exc:
        logger.error(f"Warmup: Failed to initialize LLM provider: {exc}")
        return False


def _init_achievement_system_sync() -> bool:
    """Initialize the achievement system."""
    global _achievement_system
    try:
        start = time.time()
        logger.info("Warmup: Initializing achievement system...")
        _achievement_system = AchievementSystem()
        elapsed = (time.time() - start) * 1000
        logger.info(f"Warmup: Achievement system ready in {elapsed:.0f}ms")
        return True
    except Exception as exc:
        logger.error(f"Warmup: Failed to initialize achievement system: {exc}")
        return False


def _init_vector_store_sync() -> bool:
    """Initialize the vector store without loading its model."""
    global _vector_store
    try:
        start = time.time()
        logger.info("Warmup: Initializing vector store (lazy mode)...")
        _vector_store = LocalVectorStore(lazy_load=True)
        elapsed = (time.time() - start) * 1000
        if _vector_store.is_available():
            logger.info(
                f"Warmup: Vector store initialized in {elapsed:.0f}ms "
                "(model will load on first use)"
            )
        else:
            logger.warning(
                "Warmup: Vector store initialized but dependencies are missing"
            )
        return True
    except Exception as exc:
        logger.error(f"Warmup: Failed to initialize vector store: {exc}")
        return False


def warmup_providers(timeout_seconds: float = 30.0) -> dict[str, Any]:
    """Initialize provider clients in parallel while retaining lazy model loading."""
    with _startup_lock:
        if _startup_state["initialized"]:
            logger.info("Warmup: Already initialized, skipping")
            return _startup_state
        if _startup_state["initializing"]:
            logger.warning("Warmup: Already in progress, skipping")
            return _startup_state
        _startup_state["initializing"] = True

    start_time = time.time()
    logger.info("=" * 60)
    logger.info("WARMUP: Starting provider initialization...")
    logger.info("=" * 60)
    errors = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            "speech": executor.submit(_init_speech_provider_sync),
            "llm": executor.submit(_init_llm_provider_sync),
            "achievement": executor.submit(_init_achievement_system_sync),
            "vector_store": executor.submit(_init_vector_store_sync),
        }
        for name, future in futures.items():
            try:
                remaining_time = timeout_seconds - (time.time() - start_time)
                if remaining_time <= 0:
                    raise FutureTimeoutError("Overall timeout exceeded")
                success = future.result(timeout=remaining_time)
                _startup_state["providers_ready"][name] = success
                if not success:
                    errors.append(f"{name} initialization failed")
            except FutureTimeoutError:
                logger.error(f"Warmup: Timeout waiting for {name} provider")
                errors.append(f"{name} initialization timed out")
                _startup_state["providers_ready"][name] = False
            except Exception as exc:
                logger.error(f"Warmup: Exception initializing {name}: {exc}")
                errors.append(f"{name}: {exc}")
                _startup_state["providers_ready"][name] = False

    total_time = (time.time() - start_time) * 1000
    with _startup_lock:
        _startup_state["initialized"] = True
        _startup_state["initializing"] = False
        _startup_state["errors"] = errors
        _startup_state["startup_time_ms"] = total_time

    ready_count = sum(1 for ready in _startup_state["providers_ready"].values() if ready)
    total_count = len(_startup_state["providers_ready"])
    logger.info("=" * 60)
    logger.info(f"WARMUP COMPLETE: {ready_count}/{total_count} providers ready")
    logger.info(f"Total initialization time: {total_time:.0f}ms")
    if errors:
        logger.warning(f"Initialization errors: {errors}")
    logger.info("=" * 60)
    return _startup_state


def get_startup_state() -> dict[str, Any]:
    """Return a shallow copy of startup state."""
    return _startup_state.copy()


def is_ready() -> bool:
    """Return whether warmup has completed."""
    return _startup_state["initialized"]


def reset_providers() -> None:
    """Reset all provider singletons and warmup state."""
    global _ollama_provider, _openrouter_provider, _lmstudio_provider
    global _speech_provider, _achievement_system, _vector_store
    global _startup_state

    with _startup_lock:
        _ollama_provider = None
        _openrouter_provider = None
        _lmstudio_provider = None
        _speech_provider = None
        _achievement_system = None
        _vector_store = None
        _startup_state = {
            "initialized": False,
            "initializing": False,
            "providers_ready": {
                "speech": False,
                "llm": False,
                "achievement": False,
                "vector_store": False,
            },
            "errors": [],
            "startup_time_ms": 0,
        }

    logger.info("All providers reset")


def reset_llm_providers() -> None:
    """Drop cached LLM clients after their database settings change."""
    global _ollama_provider, _openrouter_provider, _lmstudio_provider
    _ollama_provider = None
    _openrouter_provider = None
    _lmstudio_provider = None
