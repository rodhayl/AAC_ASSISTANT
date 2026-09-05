"""Lazy provider singletons and startup warmup orchestration."""

import asyncio
import inspect
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, TypedDict

from fastapi import Depends
from loguru import logger

from src import config
from src.aac_app.providers.groq_provider import GroqProvider
from src.aac_app.providers.lmstudio_provider import LMStudioProvider
from src.aac_app.providers.local_speech_provider import (
    DEFAULT_STT_MODEL,
    LocalSpeechProvider,
    normalize_stt_model,
)
from src.aac_app.providers.ollama_provider import OllamaProvider
from src.aac_app.providers.openrouter_provider import OpenRouterProvider
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.board_generation_service import BoardGenerationService
from src.aac_app.services.learning.service import LearningCompanionService
from src.aac_app.services.local_vector_store import (
    LocalVectorStore,
    vector_store_operation_lock,
)
from src.aac_app.services.symbol_svg_autogen import set_llm_provider_factory
from src.api import deps as deps_package

# Background SVG auto-generation (Smartbar text-only words) needs the same
# provider instance the request path uses. Register the factory lazily so
# the module stays import-safe: the factory only calls back into this module
# when a background thread actually needs to generate.
set_llm_provider_factory(lambda: get_llm_provider())

_ollama_provider: OllamaProvider | None = None
_openrouter_provider: OpenRouterProvider | None = None
_lmstudio_provider: LMStudioProvider | None = None
_groq_provider: GroqProvider | None = None
_speech_provider: LocalSpeechProvider | None = None
_achievement_system: AchievementSystem | None = None
_vector_store: LocalVectorStore | None = None
_deferred_vector_store_events: list[threading.Event] = []

def _new_startup_state() -> dict[str, Any]:
    """Create an isolated startup snapshot for initialization and resets."""
    return {
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
        "provider_metrics": {},
    }


_startup_state: dict[str, Any] = _new_startup_state()
_startup_lock = threading.Lock()
_startup_generation = 0
_warmup_generation_local = threading.local()

# Guards the check-and-create pattern in the get_*_provider singleton
# getters so the warmup thread and request threads cannot race-construct
# the same provider.
_provider_lock = threading.Lock()

# ``asyncio.to_thread`` cannot cancel native model cleanup once it starts. Use
# dedicated daemon workers instead of the loop's shared executor, and retain
# references until each release finishes so a timed-out cleanup is observable
# and cannot be mistaken for a completed release.
_speech_release_lock = threading.Lock()


@dataclass
class _SpeechReleaseState:
    """Tracked native speech cleanup for one provider instance."""

    completed: threading.Event
    failure: list[BaseException]
    thread: threading.Thread | None = None


_speech_release_workers: dict[int, _SpeechReleaseState] = {}

# Third-party providers may expose only an async ``close`` method. Keep the
# fallback tasks strongly referenced until completion so a loop cannot collect
# them before the transport has been released.
_pending_llm_close_tasks: set[asyncio.Task[Any]] = set()


def _consume_llm_close_task(task: asyncio.Task[Any]) -> None:
    """Consume and log failures from a fallback async provider close."""
    _pending_llm_close_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("LLM provider cleanup failed: {}", exc)


def _close_vector_store(store: LocalVectorStore | None) -> None:
    """Release a discarded vector store without disposing the shared DB engine."""
    close = getattr(store, "close", None)
    if callable(close):
        try:
            close()
        except Exception as exc:
            logger.warning("Vector store cleanup failed: {}", exc)


def _start_deferred_vector_store_close(
    store: LocalVectorStore | None,
    completed: threading.Event,
) -> None:
    """Close one already-registered store after vector operations release."""
    if store is None:
        with _provider_lock:
            _deferred_vector_store_events.remove(completed)
        completed.set()
        return

    def close_store() -> None:
        global _vector_store
        try:
            with vector_store_operation_lock:
                with _provider_lock:
                    if _vector_store is store:
                        _vector_store = None
                _close_vector_store(store)
        finally:
            with _provider_lock:
                if completed in _deferred_vector_store_events:
                    _deferred_vector_store_events.remove(completed)
            completed.set()

    try:
        threading.Thread(
            target=close_store,
            name="aac-vector-store-cleanup",
            daemon=True,
        ).start()
    except Exception as exc:
        # Do not strand a pending event if thread creation is unavailable.
        logger.warning("Could not start deferred vector-store cleanup: {}", exc)
        close_store()


def _defer_vector_store_for_reset() -> threading.Event:
    """Register vector cleanup without detaching an active operation's store."""
    global _vector_store
    completed = threading.Event()

    # If no operation owns the lock, detach immediately. Otherwise leave the
    # store attached so the active worker can make nested getter calls; the
    # cleanup worker will detach it atomically after the operation completes.
    operation_is_active = _vector_store_lock_owned()
    if not operation_is_active:
        operation_is_active = not vector_store_operation_lock.acquire(blocking=False)
    try:
        with _provider_lock:
            store = _vector_store
            if not operation_is_active:
                _vector_store = None
            _deferred_vector_store_events.append(completed)
    finally:
        if not operation_is_active:
            vector_store_operation_lock.release()

    _start_deferred_vector_store_close(store, completed)
    return completed


def _detach_vector_store_for_reset(*, close: bool) -> None:
    """Detach a vector store without closing it underneath an active operation."""
    global _vector_store
    if not vector_store_operation_lock.acquire(blocking=False):
        if close:
            completed = threading.Event()
            with _provider_lock:
                # Keep the store attached while its current operation owns the
                # reentrant lock. This lets nested callers continue using the
                # in-flight instance; cleanup clears it only after the lock is
                # released, avoiding both use-after-close and transient 500s.
                store = _vector_store
                _deferred_vector_store_events.append(completed)
            _start_deferred_vector_store_close(store, completed)
            logger.warning(
                "Vector-store operation active; deferring provider reset for that store"
            )
        return
    try:
        with _provider_lock:
            store = _vector_store
            if close:
                _vector_store = None
        if close:
            _close_vector_store(store)
    finally:
        vector_store_operation_lock.release()


class ProviderMetric(TypedDict):
    """Readiness telemetry for one provider initialization attempt.

    ``duration_ms`` is nullable when the caller's timeout expires before the
    worker reports its completion. Consumers should use ``timed_out`` to
    distinguish that case from a completed attempt.
    """

    success: bool
    duration_ms: float | None
    timed_out: bool


@dataclass(frozen=True)
class _InitializationResult:
    success: bool
    duration_ms: float
    error: Exception | None = None


def _get_setting_value(key: str, default: str = "") -> str:
    """Resolve through the package facade so tests and callers can override it."""
    return deps_package.get_setting_value(key, default)


def _close_llm_provider(provider: Any | None) -> None:
    """Release HTTP transports from a synchronous cleanup path."""
    close_sync = getattr(provider, "close_sync", None)
    if callable(close_sync):
        try:
            close_sync()
        except Exception as exc:
            logger.warning("LLM provider cleanup failed: {}", exc)
        return

    close = getattr(provider, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if not inspect.isawaitable(result):
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(result)
        else:
            # This fallback is only for third-party providers without a
            # close_sync method; concrete providers use the awaited path below.
            task = asyncio.create_task(result)
            _pending_llm_close_tasks.add(task)
            task.add_done_callback(_consume_llm_close_task)
    except Exception as exc:
        logger.warning("LLM provider cleanup failed: {}", exc)


async def _close_llm_provider_async(provider: Any | None) -> None:
    """Release a provider while an application event loop is running."""
    close_async = getattr(provider, "close_async", None)
    if callable(close_async):
        try:
            result = close_async()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.warning("LLM provider cleanup failed: {}", exc)
        return

    close = getattr(provider, "close", None)
    if callable(close):
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.warning("LLM provider cleanup failed: {}", exc)
        return

    close_sync = getattr(provider, "close_sync", None)
    if callable(close_sync):
        try:
            close_sync()
        except Exception as exc:
            logger.warning("LLM provider cleanup failed: {}", exc)


# Public alias for routers that create short-lived provider clients (e.g.
# settings model listing). The canonical best-effort async cleanup lives here
# so routers do not reimplement it.
close_provider_async = _close_llm_provider_async


def get_ollama_provider() -> OllamaProvider:
    """Return the configured Ollama provider singleton."""
    global _ollama_provider

    base_url = _get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL)
    model = _get_setting_value("ollama_model", "")
    discarded: Any | None = None

    with _provider_lock:
        if _ollama_provider is None:
            logger.info(
                f"Initializing global OllamaProvider with base_url={base_url}, model={model}"
            )
            _ollama_provider = OllamaProvider(base_url=base_url, model=model)
        elif (
            _ollama_provider.base_url != base_url
            or _ollama_provider._configured_model != model
        ):
            logger.info(
                "Ollama settings changed. Re-initializing provider. "
                f"(URL: {_ollama_provider.base_url}->{base_url}, "
                f"Model: {_ollama_provider.recommended_model}->{model})"
            )
            discarded = _ollama_provider
            _ollama_provider = OllamaProvider(base_url=base_url, model=model)
        provider = _ollama_provider

    _close_llm_provider(discarded)
    return provider


def get_openrouter_provider() -> OpenRouterProvider:
    """Return the configured OpenRouter provider singleton."""
    global _openrouter_provider

    api_key = _get_setting_value("openrouter_api_key", "")
    model = _get_setting_value("openrouter_model", "")
    discarded: Any | None = None

    with _provider_lock:
        if _openrouter_provider is None:
            logger.info("Initializing global OpenRouterProvider")
            _openrouter_provider = OpenRouterProvider(api_key=api_key, model=model)
        elif (
            _openrouter_provider.api_key != api_key
            or _openrouter_provider._configured_model != model
        ):
            logger.info("OpenRouter settings changed. Re-initializing provider.")
            discarded = _openrouter_provider
            _openrouter_provider = OpenRouterProvider(api_key=api_key, model=model)
        provider = _openrouter_provider

    _close_llm_provider(discarded)
    return provider


def get_lmstudio_provider() -> LMStudioProvider:
    """Return the configured LM Studio provider singleton."""
    global _lmstudio_provider

    base_url = _get_setting_value("lmstudio_base_url", config.LMSTUDIO_BASE_URL)
    model = _get_setting_value("lmstudio_model", "")
    discarded: Any | None = None

    with _provider_lock:
        if _lmstudio_provider is None:
            logger.info("Initializing global LMStudioProvider")
            _lmstudio_provider = LMStudioProvider(base_url=base_url, model=model)
        else:
            current_url = _lmstudio_provider.base_url.rstrip("/")
            new_url = base_url.rstrip("/")
            if current_url != new_url or _lmstudio_provider._configured_model != model:
                logger.info(
                    f"LM Studio settings changed. Re-initializing provider. "
                    f"(URL: {current_url}->{new_url})"
                )
                discarded = _lmstudio_provider
                _lmstudio_provider = LMStudioProvider(base_url=base_url, model=model)
        provider = _lmstudio_provider

    _close_llm_provider(discarded)
    return provider


def get_groq_provider() -> GroqProvider:
    """Return the configured Groq provider singleton."""
    global _groq_provider

    api_key = _get_setting_value("groq_api_key", "")
    model = _get_setting_value("groq_model", "")
    discarded: Any | None = None

    with _provider_lock:
        if _groq_provider is None:
            logger.info("Initializing global GroqProvider")
            _groq_provider = GroqProvider(api_key=api_key, model=model)
        elif (
            _groq_provider.api_key != api_key
            or _groq_provider._configured_model != model
        ):
            logger.info("Groq settings changed. Re-initializing provider.")
            discarded = _groq_provider
            _groq_provider = GroqProvider(api_key=api_key, model=model)
        provider = _groq_provider

    _close_llm_provider(discarded)
    return provider


def get_llm_provider() -> (
    OllamaProvider | OpenRouterProvider | LMStudioProvider | GroqProvider
):
    """Return the configured primary LLM provider."""
    provider_type = (
        "groq"
        if config.ENVIRONMENT.strip().casefold() == "production"
        else _get_setting_value("ai_provider", "ollama")
    )

    if provider_type == "openrouter":
        provider = get_openrouter_provider()
    elif provider_type == "lmstudio":
        provider = get_lmstudio_provider()
    elif provider_type == "groq":
        provider = get_groq_provider()
    else:
        provider = get_ollama_provider()

    return provider


def _release_speech_provider(provider: Any | None) -> None:
    """Release an STT provider when its cached instance is discarded."""
    release = getattr(provider, "release", None)
    if not callable(release):
        return

    # Avoid a synchronous settings/reset path releasing an instance already
    # owned by an asynchronous shutdown worker. The async worker remains the
    # single owner of that native release operation.
    provider_key = id(provider)
    with _speech_release_lock:
        existing = _speech_release_workers.get(provider_key)
    if existing is not None and not existing.completed.is_set():
        logger.debug("Speech provider release already in progress")
        return

    try:
        release()
    except Exception as exc:
        # Cleanup must never prevent a new provider from being installed
        # or make a settings/reset endpoint fail.
        logger.warning("Speech provider cleanup failed: {}", exc)


async def _drain_speech_release_workers(timeout: float) -> None:
    """Wait briefly for previously timed-out native release workers."""
    deadline = asyncio.get_running_loop().time() + max(timeout, 0.0)
    while True:
        with _speech_release_lock:
            workers = [
                state.thread
                for state in _speech_release_workers.values()
                if state.thread is not None and state.thread.is_alive()
            ]
        if not workers:
            return
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            logger.warning(
                "Speech cleanup worker(s) still running after shutdown budget: {}",
                len(workers),
            )
            return
        await asyncio.sleep(min(remaining, 0.05))


async def _release_speech_provider_async(provider: Any | None, timeout: float) -> None:
    """Release speech resources without allowing shutdown to hang.

    Native model release hooks cannot be force-cancelled safely. A dedicated
    daemon thread keeps a blocked optional provider from occupying asyncio's
    shared worker pool; the worker remains tracked until it finishes, while the
    event loop waits only for the configured shutdown budget.
    """
    release = getattr(provider, "release", None)
    if not callable(release):
        return

    provider_key = id(provider)
    with _speech_release_lock:
        state = _speech_release_workers.get(provider_key)
        if state is None or state.completed.is_set():
            state = _SpeechReleaseState(
                completed=threading.Event(),
                failure=[],
            )
            _speech_release_workers[provider_key] = state
            start_worker = True
        else:
            start_worker = False

    if start_worker:
        def run_release() -> None:
            try:
                release()
            except BaseException as exc:  # cleanup must not escape a daemon thread
                state.failure.append(exc)
            finally:
                state.completed.set()
                with _speech_release_lock:
                    if _speech_release_workers.get(provider_key) is state:
                        _speech_release_workers.pop(provider_key, None)

        worker = threading.Thread(
            target=run_release,
            name="aac-speech-release",
            daemon=True,
        )
        state.thread = worker
        try:
            worker.start()
        except BaseException:
            with _speech_release_lock:
                if _speech_release_workers.get(provider_key) is state:
                    _speech_release_workers.pop(provider_key, None)
            raise

    deadline = asyncio.get_running_loop().time() + max(timeout, 0.0)
    completed = state.completed
    while not completed.is_set():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            logger.warning(
                "Timed out releasing speech provider during shutdown; "
                "dedicated cleanup worker remains tracked"
            )
            return
        await asyncio.sleep(min(remaining, 0.05))

    if state.failure:
        logger.warning("Speech provider cleanup failed: {}", state.failure[0])


def get_speech_provider() -> LocalSpeechProvider:
    """Return the configured local speech provider singleton."""
    global _speech_provider
    configured_model = normalize_stt_model(_get_setting_value("stt_model", DEFAULT_STT_MODEL))
    discarded: Any | None = None
    with _provider_lock:
        if _speech_provider is None:
            logger.info("Initializing global LocalSpeechProvider with model {}", configured_model)
            _speech_provider = LocalSpeechProvider(model_size=configured_model)
        elif _speech_provider.model_size != configured_model:
            logger.info(
                "STT model changed. Re-initializing LocalSpeechProvider ({} -> {})",
                _speech_provider.model_size,
                configured_model,
            )
            discarded = _speech_provider
            _speech_provider = LocalSpeechProvider(model_size=configured_model)
        provider = _speech_provider
    _release_speech_provider(discarded)
    return provider


def get_achievement_system() -> AchievementSystem:
    """Return the achievement system singleton."""
    global _achievement_system
    with _provider_lock:
        if _achievement_system is None:
            logger.info("Initializing global AchievementSystem")
            _achievement_system = AchievementSystem()
        provider = _achievement_system
    return provider


def _vector_store_lock_owned() -> bool:
    """Return whether the current thread already owns the reentrant vector lock."""
    return bool(getattr(vector_store_operation_lock, "_is_owned", lambda: False)())


def _wait_for_deferred_vector_store_cleanup() -> None:
    """Wait for reset-detached stores before allowing a replacement singleton."""
    while True:
        with _provider_lock:
            pending = list(_deferred_vector_store_events)
        if not pending:
            return
        for completed in pending:
            completed.wait()


def get_vector_store() -> LocalVectorStore:
    """Return the local vector store singleton."""
    global _vector_store

    # Wait only outside the operation/provider locks. Deferred cleanup needs
    # both locks before it can signal completion; waiting while holding either
    # lock would deadlock the cleanup worker.
    if not _vector_store_lock_owned():
        _wait_for_deferred_vector_store_cleanup()

    with vector_store_operation_lock, _provider_lock:
        if _vector_store is not None:
            return _vector_store
        if _deferred_vector_store_events:
            # A detached store is still being closed by another reset. The
            # outer wait normally handles this; keep the guard for a reset that
            # begins between that wait and lock acquisition.
            raise RuntimeError(
                "Cannot create a replacement vector store while a detached "
                "instance awaits lock release"
            )
        logger.info("Initializing global LocalVectorStore")
        _vector_store = LocalVectorStore()
        return _vector_store


def _get_llm_settings() -> tuple[int, float]:
    """Read the configured primary LLM behavior settings."""
    try:
        max_tokens = int(_get_setting_value("ai_max_tokens", str(config.AI_MAX_TOKENS)))
    except ValueError:
        max_tokens = config.AI_MAX_TOKENS

    try:
        temperature = float(_get_setting_value("ai_temperature", str(config.AI_TEMPERATURE)))
    except ValueError:
        temperature = config.AI_TEMPERATURE

    return max_tokens, temperature


def get_learning_service(
    llm: OllamaProvider | OpenRouterProvider | LMStudioProvider | GroqProvider = Depends(
        get_llm_provider
    ),
    speech: LocalSpeechProvider = Depends(get_speech_provider),
) -> LearningCompanionService:
    """Build a learning service with the configured provider defaults."""
    max_tokens, temperature = _get_llm_settings()
    if (
        config.ENVIRONMENT.strip().casefold() == "production"
        and not isinstance(llm, GroqProvider)
    ):
        raise RuntimeError("Production learning requires the configured Groq provider")
    return LearningCompanionService(
        llm,
        speech,
        default_max_tokens=max_tokens,
        default_temperature=temperature,
    )


def get_board_generation_service(
    llm: OllamaProvider | OpenRouterProvider | LMStudioProvider | GroqProvider = Depends(
        get_llm_provider
    ),
) -> BoardGenerationService:
    """Build a board-generation service with the configured LLM."""
    if (
        config.ENVIRONMENT.strip().casefold() == "production"
        and not isinstance(llm, GroqProvider)
    ):
        raise RuntimeError("Production board generation requires the configured Groq provider")
    return BoardGenerationService(llm)


def _init_speech_provider_sync() -> bool:
    """Initialize speech provider without loading its model."""
    global _speech_provider
    try:
        start = time.time()
        logger.info("Warmup: Initializing speech recognition provider (lazy mode)...")
        provider = LocalSpeechProvider(
            model_size=normalize_stt_model(_get_setting_value("stt_model", DEFAULT_STT_MODEL)),
            lazy_load=True,
        )
        with _startup_lock:
            if (
                getattr(_warmup_generation_local, "generation", None) is not None
                and _warmup_generation_local.generation != _startup_generation
            ):
                _release_speech_provider(provider)
                return False
            with _provider_lock:
                _speech_provider = provider
        elapsed = (time.time() - start) * 1000
        if provider.is_available():
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
    global _ollama_provider, _openrouter_provider, _lmstudio_provider, _groq_provider
    try:
        start = time.time()
        provider_type = (
            "groq"
            if config.ENVIRONMENT.strip().casefold() == "production"
            else _get_setting_value("ai_provider", "ollama")
        )
        logger.info(f"Warmup: Initializing {provider_type} LLM provider...")

        with _startup_lock:
            if (
                getattr(_warmup_generation_local, "generation", None) is not None
                and _warmup_generation_local.generation != _startup_generation
            ):
                return False
            with _provider_lock:
                discarded_llm: Any | None = None
                if provider_type == "openrouter":
                    discarded_llm = _openrouter_provider
                    _openrouter_provider = OpenRouterProvider(
                        api_key=_get_setting_value("openrouter_api_key", ""),
                        model=_get_setting_value("openrouter_model", ""),
                    )
                elif provider_type == "lmstudio":
                    discarded_llm = _lmstudio_provider
                    _lmstudio_provider = LMStudioProvider(
                        base_url=_get_setting_value(
                            "lmstudio_base_url", config.LMSTUDIO_BASE_URL
                        ),
                        model=_get_setting_value("lmstudio_model", ""),
                    )
                elif provider_type == "groq":
                    configured_model = _get_setting_value("groq_model", "")
                    if not configured_model:
                        raise RuntimeError(
                            "Groq provider requires an explicitly configured model"
                        )
                    discarded_llm = _groq_provider
                    _groq_provider = GroqProvider(
                        api_key=_get_setting_value("groq_api_key", ""),
                        model=configured_model,
                    )
                else:
                    discarded_llm = _ollama_provider
                    _ollama_provider = OllamaProvider(
                        base_url=_get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL),
                        model=_get_setting_value("ollama_model", ""),
                    )

        _close_llm_provider(discarded_llm)
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
        with _startup_lock:
            if (
                getattr(_warmup_generation_local, "generation", None) is not None
                and _warmup_generation_local.generation != _startup_generation
            ):
                return False
            with _provider_lock:
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
        with vector_store_operation_lock, _startup_lock:
            if (
                getattr(_warmup_generation_local, "generation", None) is not None
                and _warmup_generation_local.generation != _startup_generation
            ):
                return False
            with _provider_lock:
                previous_store = _vector_store
                vector_store = LocalVectorStore(lazy_load=True)
                _vector_store = vector_store
            _close_vector_store(previous_store)
        elapsed = (time.time() - start) * 1000
        if vector_store.is_available():
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
    already_initialized = False
    already_initializing = False
    with _startup_lock:
        if _startup_state["initialized"]:
            already_initialized = True
            generation = _startup_generation
        elif _startup_state["initializing"]:
            already_initializing = True
            generation = _startup_generation
        else:
            _startup_state["initializing"] = True
            generation = _startup_generation

    if already_initialized:
        logger.info("Warmup: Already initialized, skipping")
        return get_startup_state()
    if already_initializing:
        logger.warning("Warmup: Already in progress, skipping")
        return get_startup_state()

    start_time = time.time()
    logger.info("=" * 60)
    logger.info("WARMUP: Starting provider initialization...")
    logger.info("=" * 60)
    errors = []

    def measure_initialization(initializer) -> _InitializationResult:
        started = time.perf_counter()
        _warmup_generation_local.generation = generation
        try:
            success = initializer()
            return _InitializationResult(
                success=success,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            # Capture the provider-specific duration at the worker boundary so
            # failure telemetry never falls back to overall warmup elapsed time.
            return _InitializationResult(
                success=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=exc,
            )
        finally:
            del _warmup_generation_local.generation

    executor = ThreadPoolExecutor(max_workers=4)
    stale_generation = False
    try:
        futures = {
            "speech": executor.submit(measure_initialization, _init_speech_provider_sync),
            "llm": executor.submit(measure_initialization, _init_llm_provider_sync),
            "achievement": executor.submit(measure_initialization, _init_achievement_system_sync),
            "vector_store": executor.submit(measure_initialization, _init_vector_store_sync),
        }
        for name, future in futures.items():
            with _startup_lock:
                if generation != _startup_generation:
                    stale_generation = True
                    break
            try:
                remaining_time = timeout_seconds - (time.time() - start_time)
                if remaining_time <= 0:
                    # The overall timeout is exhausted, but the future may
                    # have already completed.  A finished future must never
                    # be falsely reported as timed out (that corrupts /ready
                    # state).
                    if future.done():
                        result = future.result()
                    else:
                        raise FutureTimeoutError("Overall timeout exceeded")
                else:
                    result = future.result(timeout=remaining_time)
                if isinstance(result, _InitializationResult):
                    success = result.success
                    duration_ms = result.duration_ms
                    error = result.error
                else:  # Compatibility with patched initializers returning tuples.
                    success, duration_ms = result
                    error = None
                with _startup_lock:
                    if generation != _startup_generation:
                        stale_generation = True
                        break
                    _startup_state["providers_ready"][name] = success
                    _startup_state["provider_metrics"][name] = ProviderMetric(
                        success=success,
                        duration_ms=round(duration_ms, 2),
                        timed_out=False,
                    )
                    if not success:
                        if error is not None:
                            # Full detail must stay server-side: /ready is
                            # public and must never receive raw exception text
                            # (URLs, paths, credentials).
                            logger.error(
                                f"Warmup: {name} provider initialization failed: {error}"
                            )
                        errors.append(f"{name} initialization failed")
            except FutureTimeoutError:
                logger.error(f"Warmup: Timeout waiting for {name} provider")
                with _startup_lock:
                    if generation != _startup_generation:
                        stale_generation = True
                        break
                    errors.append(f"{name} initialization timed out")
                    _startup_state["providers_ready"][name] = False
                    _startup_state["provider_metrics"][name] = ProviderMetric(
                        success=False,
                        # The worker may still be running, so no provider-specific
                        # duration exists yet. Never label total warmup time as it.
                        duration_ms=None,
                        timed_out=True,
                    )
            except Exception as exc:
                logger.error(f"Warmup: Exception initializing {name}: {exc}")
                with _startup_lock:
                    if generation != _startup_generation:
                        stale_generation = True
                        break
                    errors.append(f"{name} initialization failed")
                    _startup_state["providers_ready"][name] = False
                    _startup_state["provider_metrics"][name] = ProviderMetric(
                        success=False,
                        duration_ms=None,
                        timed_out=False,
                    )
    finally:
        # Do NOT wait for stuck workers — shutdown(wait=False) returns
        # immediately and cancel_futures=True cancels pending submissions.
        # Without this a single stuck worker can hold warmup far past the
        # timeout (proven: a dev run logged 92438ms with timeout_seconds=30).
        executor.shutdown(wait=False, cancel_futures=True)

    total_time = (time.time() - start_time) * 1000
    with _startup_lock:
        if generation != _startup_generation:
            stale_generation = True
        else:
            _startup_state["initialized"] = True
            _startup_state["initializing"] = False
            _startup_state["errors"] = errors
            _startup_state["startup_time_ms"] = total_time

    if stale_generation:
        logger.info("Warmup: Discarding results from a reset provider generation")
        return get_startup_state()

    ready_count = sum(1 for ready in _startup_state["providers_ready"].values() if ready)
    total_count = len(_startup_state["providers_ready"])
    logger.info("=" * 60)
    logger.info(f"WARMUP COMPLETE: {ready_count}/{total_count} providers ready")
    logger.info(f"Total initialization time: {total_time:.0f}ms")
    if errors:
        logger.warning(f"Initialization errors: {errors}")
    logger.info("=" * 60)
    return get_startup_state()


def get_startup_state() -> dict[str, Any]:
    """Return a defensive snapshot of startup state.

    Provider metrics use ``duration_ms=None`` when a worker is still running
    after the warmup deadline; ``timed_out=True`` identifies that condition.
    """
    with _startup_lock:
        return {
            **_startup_state,
            "providers_ready": dict(_startup_state["providers_ready"]),
            "errors": list(_startup_state["errors"]),
            "provider_metrics": {
                name: dict(metrics)
                for name, metrics in _startup_state["provider_metrics"].items()
            },
        }


def is_ready() -> bool:
    """Return whether warmup has completed."""
    return _startup_state["initialized"]


def reset_providers() -> None:
    """Reset all provider singletons and warmup state."""
    global _ollama_provider, _openrouter_provider, _lmstudio_provider, _groq_provider
    global _speech_provider, _achievement_system, _vector_store
    global _startup_state, _startup_generation

    with _startup_lock:
        _startup_generation += 1
        with _provider_lock:
            ollama_provider = _ollama_provider
            openrouter_provider = _openrouter_provider
            lmstudio_provider = _lmstudio_provider
            groq_provider = _groq_provider
            _ollama_provider = None
            _openrouter_provider = None
            _lmstudio_provider = None
            _groq_provider = None
            speech_provider = _speech_provider
            _speech_provider = None
            _achievement_system = None
        _startup_state = _new_startup_state()

    _release_speech_provider(speech_provider)
    _detach_vector_store_for_reset(close=True)
    for provider in (
        ollama_provider,
        openrouter_provider,
        lmstudio_provider,
        groq_provider,
    ):
        _close_llm_provider(provider)
    logger.info("All providers reset")


def reset_speech_provider() -> None:
    """Release and drop the cached STT client after settings change."""
    global _speech_provider
    with _provider_lock:
        provider = _speech_provider
        _speech_provider = None
    _release_speech_provider(provider)


def reset_llm_providers() -> None:
    """Close and drop cached LLM clients after settings changes."""
    global _ollama_provider, _openrouter_provider, _lmstudio_provider, _groq_provider
    with _provider_lock:
        providers = (
            _ollama_provider,
            _openrouter_provider,
            _lmstudio_provider,
            _groq_provider,
        )
        _ollama_provider = None
        _openrouter_provider = None
        _lmstudio_provider = None
        _groq_provider = None
    for provider in providers:
        _close_llm_provider(provider)


async def reset_providers_async(
    *, close_vector_store: bool = True, timeout_seconds: float | None = None
) -> None:
    """Reset providers and await asynchronous transports during app shutdown.

    ``close_vector_store=False`` is reserved for a shutdown path whose
    synchronous indexing worker outlives its cancelled asyncio wrapper. Closing
    that store in that case would race the worker; the process is exiting, so
    retaining the store is safer than use-after-close.
    """
    global _ollama_provider, _openrouter_provider, _lmstudio_provider, _groq_provider
    global _speech_provider, _achievement_system, _vector_store
    global _startup_state, _startup_generation

    with _startup_lock:
        _startup_generation += 1
        with _provider_lock:
            llm_providers = (
                _ollama_provider,
                _openrouter_provider,
                _lmstudio_provider,
                _groq_provider,
            )
            speech_provider = _speech_provider
            _ollama_provider = None
            _openrouter_provider = None
            _lmstudio_provider = None
            _groq_provider = None
            _speech_provider = None
            _achievement_system = None
        _startup_state = _new_startup_state()

    deferred_store_done: threading.Event | None = None
    if close_vector_store:
        _detach_vector_store_for_reset(close=True)
    else:
        # Even when shutdown must not close an active store immediately, detach
        # it from the singleton and queue it for cleanup after the operation.
        deferred_store_done = _defer_vector_store_for_reset()
        logger.warning("Deferring vector-store close until the indexing worker exits")
    shutdown_timeout = max(
        float(
            config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        ),
        0.01,
    )
    deadline = asyncio.get_running_loop().time() + shutdown_timeout
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining > 0:
        # Give previously timed-out native cleanup a first chance to finish;
        # then reserve the larger share for the provider being reset now.
        await _drain_speech_release_workers(remaining * 0.25)
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining > 0:
        await _release_speech_provider_async(speech_provider, remaining * 0.75)
    for provider in llm_providers:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            logger.warning("Skipping provider cleanup after shutdown deadline")
            break
        try:
            await asyncio.wait_for(_close_llm_provider_async(provider), timeout=remaining)
        except TimeoutError:
            logger.warning("Timed out closing LLM provider during shutdown")
        except Exception as exc:
            logger.warning("LLM provider cleanup failed: {}", exc)

    # A final check catches workers that finished while LLM transports were
    # being closed. The earlier reserved window handles the normal case.
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining > 0:
        await _drain_speech_release_workers(remaining)
    if deferred_store_done is not None:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining > 0:
            await asyncio.to_thread(deferred_store_done.wait, remaining)
    logger.info("All providers reset")
