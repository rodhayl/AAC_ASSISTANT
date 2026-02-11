import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Dict, Generator, Optional, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models.database import (
    AppSettings,
    User,
    create_engine_instance,
    create_tables,
    create_session_factory,
    get_session,
)
from src.aac_app.providers.local_speech_provider import LocalSpeechProvider
from src.aac_app.providers.local_tts_provider import LocalTTSProvider
from src.aac_app.providers.ollama_provider import OllamaProvider
from src.aac_app.providers.openrouter_provider import OpenRouterProvider
from src.aac_app.providers.lmstudio_provider import LMStudioProvider
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.board_generation_service import BoardGenerationService
from src.aac_app.services.learning_companion_service import LearningCompanionService
from src.aac_app.services.local_vector_store import LocalVectorStore
from src.aac_app.services.translation_service import get_translation_service
from src.aac_app.utils.jwt_utils import decode_access_token

# Global instances for providers to avoid re-initialization
_ollama_provider: Optional[OllamaProvider] = None
_openrouter_provider: Optional[OpenRouterProvider] = None
_lmstudio_provider: Optional[LMStudioProvider] = None
_speech_provider: Optional[LocalSpeechProvider] = None
_tts_provider: Optional[LocalTTSProvider] = None
_achievement_system: Optional[AchievementSystem] = None
_vector_store: Optional[LocalVectorStore] = None

# Startup state tracking
_startup_state: Dict[str, Any] = {
    "initialized": False,
    "initializing": False,
    "providers_ready": {
        "speech": False,
        "tts": False,
        "llm": False,
        "achievement": False,
        "vector_store": False,
    },
    "errors": [],
    "startup_time_ms": 0,
}
_startup_lock = threading.Lock()

_tables_initialized_url: Optional[str] = None
_tables_initialized_engine_id: Optional[int] = None
_tables_init_lock = threading.Lock()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get a database session.
    Auto-commits on success, rolls back on exception.
    """
    global _tables_initialized_url, _tables_initialized_engine_id
    engine = create_engine_instance()
    engine_url = str(engine.url)
    engine_id = id(engine)
    if (
        _tables_initialized_url != engine_url
        or _tables_initialized_engine_id != engine_id
    ):
        with _tables_init_lock:
            if (
                _tables_initialized_url != engine_url
                or _tables_initialized_engine_id != engine_id
            ):
                create_tables()
                _tables_initialized_url = engine_url
                _tables_initialized_engine_id = engine_id

    session_local = create_session_factory()
    db = session_local()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def validate_token(token: str, db: Session) -> Optional[User]:
    """
    Validate JWT token and return user.

    Decodes and validates the JWT signature and expiration.
    Extracts user_id from the token payload and fetches the user from database.

    Args:
        token: JWT token string
        db: Database session

    Returns:
        User object if token is valid and user exists, None otherwise
    """
    if not token:
        return None

    # Decode and validate the JWT token
    payload = decode_access_token(token)
    if not payload:
        logger.debug("Token validation failed: Invalid or expired token")
        return None

    # Extract user_id from token payload
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Token payload missing user_id claim")
        return None

    # Fetch user from database
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"Token valid but user {user_id} not found in database")
            return None

        return user
    except Exception as e:
        logger.error(f"Database error while validating token: {e}")
        return None


def get_text(
    user: Optional[User] = None,
    key: str = "errors.unknown",
    accept_language: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Get translated text for the given key.
    Uses user settings if available, otherwise accept_language header, or defaults to English.
    """
    service = get_translation_service()
    lang = service.resolve_language(user, accept_language)
    return service.get(lang, "common", key, **kwargs)


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from JWT token.

    Validates the JWT signature and expiration, then fetches the user.

    Args:
        token: JWT token from Authorization header
        db: Database session

    Returns:
        User object if authentication successful

    Raises:
        HTTPException: 401 if token is invalid, expired, or user not found
    """
    accept_language = request.headers.get("accept-language")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=get_text(
            key="errors.credentialsInvalid", accept_language=accept_language
        ),
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        logger.debug("No token provided in request")
        raise credentials_exception

    user = validate_token(token, db)
    if user is None:
        logger.debug("Token validation failed")
        raise credentials_exception

    logger.debug(f"Authenticated user: {user.username} (id={user.id})")
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current user and verify they are active.

    Args:
        current_user: The authenticated user from get_current_user

    Returns:
        User object if user is active

    Raises:
        HTTPException: 403 if user account is not active
    """
    if not current_user.is_active:
        logger.warning(f"Inactive user attempted access: {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(user=current_user, key="errors.inactiveAccount"),
        )
    return current_user


def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(user=current_user, key="errors.insufficientPrivileges"),
        )
    return current_user


def get_current_admin_or_teacher_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(user=current_user, key="errors.insufficientPrivileges"),
        )
    return current_user


def get_setting_value(key: str, default: str = "") -> str:
    """Helper to get a setting value from database"""
    try:
        with get_session() as db:
            setting = (
                db.query(AppSettings).filter(AppSettings.setting_key == key).first()
            )
            return setting.setting_value if setting else default
    except Exception as e:
        logger.warning(f"Failed to get setting {key}: {e}")
        return default


def get_ollama_provider() -> OllamaProvider:
    """
    Dependency to get the Ollama provider instance.
    """
    global _ollama_provider
    
    base_url = get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL)
    model = get_setting_value("ollama_model", "")
    
    if _ollama_provider is None:
        logger.info(
            f"Initializing global OllamaProvider with base_url={base_url}, model={model}"
        )
        _ollama_provider = OllamaProvider(base_url=base_url, model=model)
    else:
        # Check if settings have changed
        if _ollama_provider.base_url != base_url or _ollama_provider.recommended_model != model:
            logger.info(f"Ollama settings changed. Re-initializing provider. (URL: {_ollama_provider.base_url}->{base_url}, Model: {_ollama_provider.recommended_model}->{model})")
            _ollama_provider = OllamaProvider(base_url=base_url, model=model)
            
    return _ollama_provider


def get_openrouter_provider() -> OpenRouterProvider:
    """
    Dependency to get the OpenRouter provider instance.
    """
    global _openrouter_provider
    
    api_key = get_setting_value("openrouter_api_key", "")
    model = get_setting_value("openrouter_model", "")
    
    if _openrouter_provider is None:
        logger.info("Initializing global OpenRouterProvider")
        _openrouter_provider = OpenRouterProvider(api_key=api_key, model=model)
    else:
        # Check if settings have changed
        if _openrouter_provider.api_key != api_key or _openrouter_provider.default_model != model:
            logger.info("OpenRouter settings changed. Re-initializing provider.")
            _openrouter_provider = OpenRouterProvider(api_key=api_key, model=model)
            
    return _openrouter_provider


def get_lmstudio_provider() -> LMStudioProvider:
    """
    Dependency to get the LM Studio provider instance.
    """
    global _lmstudio_provider
    
    base_url = get_setting_value("lmstudio_base_url", "http://localhost:1234/v1")
    model = get_setting_value("lmstudio_model", "")
    
    if _lmstudio_provider is None:
        logger.info("Initializing global LMStudioProvider")
        _lmstudio_provider = LMStudioProvider(base_url=base_url, model=model)
    else:
        # Check if settings have changed
        # Normalize URLs by stripping trailing slash for comparison
        current_url = _lmstudio_provider.base_url.rstrip("/")
        new_url = base_url.rstrip("/")
        
        if current_url != new_url or _lmstudio_provider.default_model != model:
            logger.info(f"LM Studio settings changed. Re-initializing provider. (URL: {current_url}->{new_url})")
            _lmstudio_provider = LMStudioProvider(base_url=base_url, model=model)
            
    return _lmstudio_provider


def get_fallback_ollama_provider() -> OllamaProvider:
    """
    Get fallback Ollama provider instance.
    """
    base_url = get_setting_value("fallback_ollama_base_url", config.OLLAMA_BASE_URL)
    model = get_setting_value("fallback_ollama_model", "")
    logger.info(
        f"Creating fallback OllamaProvider with base_url={base_url}, model={model}"
    )
    return OllamaProvider(base_url=base_url, model=model)


def get_fallback_openrouter_provider() -> OpenRouterProvider:
    """
    Get fallback OpenRouter provider instance.
    """
    api_key = get_setting_value("fallback_openrouter_api_key", "")
    logger.info("Creating fallback OpenRouterProvider")
    return OpenRouterProvider(api_key=api_key)


def get_fallback_lmstudio_provider() -> LMStudioProvider:
    """
    Get fallback LM Studio provider instance.
    """
    base_url = get_setting_value("fallback_lmstudio_base_url", "http://localhost:1234/v1")
    model = get_setting_value("fallback_lmstudio_model", "")
    logger.info("Creating fallback LMStudioProvider")
    return LMStudioProvider(base_url=base_url, model=model)


def get_fallback_llm_provider() -> Union[OllamaProvider, OpenRouterProvider, LMStudioProvider, None]:
    """
    Get the configured fallback LLM provider based on settings.
    Returns None if no fallback is configured.
    """
    provider_type = get_setting_value("fallback_ai_provider", "")

    if not provider_type:
        return None

    if provider_type == "openrouter":
        return get_fallback_openrouter_provider()
    elif provider_type == "lmstudio":
        return get_fallback_lmstudio_provider()
    else:
        return get_fallback_ollama_provider()


def get_llm_provider() -> Union[OllamaProvider, OpenRouterProvider, LMStudioProvider]:
    """
    Dependency to get the configured LLM provider based on settings.
    Falls back to fallback provider if primary provider fails.
    """
    provider_type = get_setting_value("ai_provider", "ollama")

    try:
        if provider_type == "openrouter":
            provider = get_openrouter_provider()
        elif provider_type == "lmstudio":
            provider = get_lmstudio_provider()
        else:
            provider = get_ollama_provider()

        # Check if provider is available
        if hasattr(provider, "is_available") and not provider.is_available():
            logger.warning(
                f"Primary provider {provider_type} not available, trying fallback"
            )
            fallback = get_fallback_llm_provider()
            if fallback:
                return fallback

        return provider
    except Exception as e:
        logger.error(
            f"Error with primary provider {provider_type}: {e}, trying fallback"
        )
        fallback = get_fallback_llm_provider()
        if fallback:
            return fallback
        # If fallback also fails, return primary provider (will fail gracefully in service)
        if provider_type == "openrouter":
            return get_openrouter_provider()
        elif provider_type == "lmstudio":
            return get_lmstudio_provider()
        else:
            return get_ollama_provider()


def get_speech_provider() -> LocalSpeechProvider:
    """
    Dependency to get the Speech provider instance.
    """
    global _speech_provider
    if _speech_provider is None:
        logger.info("Initializing global LocalSpeechProvider")
        _speech_provider = LocalSpeechProvider()
    return _speech_provider


def get_tts_provider() -> LocalTTSProvider:
    """
    Dependency to get the TTS provider instance.
    """
    global _tts_provider
    if _tts_provider is None:
        logger.info("Initializing global LocalTTSProvider")
        _tts_provider = LocalTTSProvider()
    return _tts_provider


def get_achievement_system() -> AchievementSystem:
    """
    Dependency to get the Achievement System instance.
    """
    global _achievement_system
    if _achievement_system is None:
        logger.info("Initializing global AchievementSystem")
        _achievement_system = AchievementSystem()
    return _achievement_system


def get_vector_store() -> LocalVectorStore:
    """
    Dependency to get the Local Vector Store instance.
    """
    global _vector_store
    if _vector_store is None:
        logger.info("Initializing global LocalVectorStore")
        _vector_store = LocalVectorStore()
    return _vector_store


def _get_llm_settings(
    llm: Union[OllamaProvider, OpenRouterProvider, LMStudioProvider],
) -> tuple[int, float]:
    """Determine LLM settings (max_tokens, temperature) based on provider type and fallback configuration."""
    primary_provider_type = get_setting_value("ai_provider", "ollama")
    fallback_provider_type = get_setting_value("fallback_ai_provider", "")

    use_fallback = False
    if fallback_provider_type:
        if (
            isinstance(llm, OpenRouterProvider)
            and fallback_provider_type == "openrouter"
            and primary_provider_type != "openrouter"
        ):
            use_fallback = True
        elif (
            isinstance(llm, LMStudioProvider)
            and fallback_provider_type == "lmstudio"
            and primary_provider_type != "lmstudio"
        ):
            use_fallback = True
        elif (
            isinstance(llm, OllamaProvider)
            and fallback_provider_type == "ollama"
            and primary_provider_type != "ollama"
        ):
            use_fallback = True

    prefix = "fallback_ai" if use_fallback else "ai"
    default_tokens = 256 if use_fallback else 1024
    default_temp = 0.3 if use_fallback else 0.5

    try:
        max_tokens = int(get_setting_value(f"{prefix}_max_tokens", str(default_tokens)))
    except ValueError:
        max_tokens = default_tokens

    try:
        temperature = float(
            get_setting_value(f"{prefix}_temperature", str(default_temp))
        )
    except ValueError:
        temperature = default_temp

    if use_fallback:
        logger.info(
            f"Using fallback LLM settings: max_tokens={max_tokens}, temperature={temperature}"
        )

    return max_tokens, temperature


def get_learning_service(
    llm: Union[OllamaProvider, OpenRouterProvider, LMStudioProvider] = Depends(get_llm_provider),
    speech: LocalSpeechProvider = Depends(get_speech_provider),
    tts: LocalTTSProvider = Depends(get_tts_provider),
) -> LearningCompanionService:
    """
    Dependency to get the Learning Companion Service.
    Uses fallback settings if the provider is a fallback provider.
    """
    max_tokens, temperature = _get_llm_settings(llm)

    return LearningCompanionService(
        llm,
        speech,
        tts,
        default_max_tokens=max_tokens,
        default_temperature=temperature,
    )


def get_board_generation_service(
    llm: Union[OllamaProvider, OpenRouterProvider, LMStudioProvider] = Depends(get_llm_provider),
) -> BoardGenerationService:
    """
    Dependency to get the Board Generation Service.
    """
    return BoardGenerationService(llm)


# ============================================================================
# STARTUP WARMUP FUNCTIONS
# ============================================================================


def _init_speech_provider_sync() -> bool:
    """Initialize speech provider (Whisper model) - uses lazy loading for fast startup."""
    global _speech_provider
    try:
        start = time.time()
        logger.info("Warmup: Initializing speech recognition provider (lazy mode)...")
        # Initialize with lazy_load=True - model won't load until first use
        _speech_provider = LocalSpeechProvider(lazy_load=True)
        elapsed = (time.time() - start) * 1000
        # Check if Whisper is even available
        if _speech_provider.is_available():
            logger.info(f"Warmup: Speech provider initialized in {elapsed:.0f}ms (model will load on first use)")
        else:
            logger.warning(f"Warmup: Speech provider initialized but Whisper is not installed")
        return True
    except Exception as e:
        logger.error(f"Warmup: Failed to initialize speech provider: {e}")
        return False


def _init_tts_provider_sync() -> bool:
    """Initialize TTS provider."""
    global _tts_provider
    try:
        start = time.time()
        logger.info("Warmup: Initializing TTS engine...")
        _tts_provider = LocalTTSProvider()
        elapsed = (time.time() - start) * 1000
        logger.info(f"Warmup: TTS provider ready in {elapsed:.0f}ms")
        return True
    except Exception as e:
        logger.error(f"Warmup: Failed to initialize TTS provider: {e}")
        return False


def _init_llm_provider_sync() -> bool:
    """Initialize LLM provider based on settings."""
    global _ollama_provider, _openrouter_provider, _lmstudio_provider
    try:
        start = time.time()
        provider_type = get_setting_value("ai_provider", "ollama")
        logger.info(f"Warmup: Initializing {provider_type} LLM provider...")

        if provider_type == "openrouter":
            api_key = get_setting_value("openrouter_api_key", "")
            _openrouter_provider = OpenRouterProvider(api_key=api_key)
        elif provider_type == "lmstudio":
            base_url = get_setting_value("lmstudio_base_url", "http://localhost:1234/v1")
            model = get_setting_value("lmstudio_model", "")
            _lmstudio_provider = LMStudioProvider(base_url=base_url, model=model)
        else:
            base_url = get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL)
            model = get_setting_value("ollama_model", "")
            _ollama_provider = OllamaProvider(base_url=base_url, model=model)

        elapsed = (time.time() - start) * 1000
        logger.info(f"Warmup: LLM provider ({provider_type}) ready in {elapsed:.0f}ms")
        return True
    except Exception as e:
        logger.error(f"Warmup: Failed to initialize LLM provider: {e}")
        return False


def _init_achievement_system_sync() -> bool:
    """Initialize achievement system."""
    global _achievement_system
    try:
        start = time.time()
        logger.info("Warmup: Initializing achievement system...")
        _achievement_system = AchievementSystem()
        elapsed = (time.time() - start) * 1000
        logger.info(f"Warmup: Achievement system ready in {elapsed:.0f}ms")
        return True
    except Exception as e:
        logger.error(f"Warmup: Failed to initialize achievement system: {e}")
        return False


def _init_vector_store_sync() -> bool:
    """Initialize vector store - uses lazy loading for fast startup."""
    global _vector_store
    try:
        start = time.time()
        logger.info("Warmup: Initializing vector store (lazy mode)...")
        # Initialize with lazy_load=True - model won't load until first search/add
        _vector_store = LocalVectorStore(lazy_load=True)
        elapsed = (time.time() - start) * 1000
        if _vector_store.is_available():
            logger.info(f"Warmup: Vector store initialized in {elapsed:.0f}ms (model will load on first use)")
        else:
            logger.warning(f"Warmup: Vector store initialized but dependencies missing")
        return True
    except Exception as e:
        logger.error(f"Warmup: Failed to initialize vector store: {e}")
        return False


def warmup_providers(timeout_seconds: float = 30.0) -> Dict[str, Any]:
    """
    Eagerly initialize all providers at startup.

    This prevents the first request from being slow due to lazy initialization,
    and avoids potential deadlocks when multiple requests arrive during init.

    Args:
        timeout_seconds: Maximum time to wait for initialization

    Returns:
        Dict with initialization status and timing
    """
    # global _startup_state  # Not needed for dict mutation

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

    # Use ThreadPoolExecutor for parallel initialization with timeout
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all initialization tasks
        futures = {
            "speech": executor.submit(_init_speech_provider_sync),
            "tts": executor.submit(_init_tts_provider_sync),
            "llm": executor.submit(_init_llm_provider_sync),
            "achievement": executor.submit(_init_achievement_system_sync),
            "vector_store": executor.submit(_init_vector_store_sync),
        }

        # Wait for all tasks with timeout
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
            except Exception as e:
                logger.error(f"Warmup: Exception initializing {name}: {e}")
                errors.append(f"{name}: {str(e)}")
                _startup_state["providers_ready"][name] = False

    # Calculate total time
    total_time = (time.time() - start_time) * 1000

    with _startup_lock:
        _startup_state["initialized"] = True
        _startup_state["initializing"] = False
        _startup_state["errors"] = errors
        _startup_state["startup_time_ms"] = total_time

    # Log summary
    ready_count = sum(1 for v in _startup_state["providers_ready"].values() if v)
    total_count = len(_startup_state["providers_ready"])

    logger.info("=" * 60)
    logger.info(f"WARMUP COMPLETE: {ready_count}/{total_count} providers ready")
    logger.info(f"Total initialization time: {total_time:.0f}ms")
    if errors:
        logger.warning(f"Initialization errors: {errors}")
    logger.info("=" * 60)

    return _startup_state


def get_startup_state() -> Dict[str, Any]:
    """Get the current startup/warmup state."""
    return _startup_state.copy()


def is_ready() -> bool:
    """Check if all critical providers are initialized."""
    return _startup_state["initialized"]


def reset_providers():
    """Reset all providers (for testing or re-initialization)."""
    global _ollama_provider, _openrouter_provider, _lmstudio_provider, _speech_provider
    global _tts_provider, _achievement_system, _vector_store, _startup_state

    with _startup_lock:
        _ollama_provider = None
        _openrouter_provider = None
        _lmstudio_provider = None
        _speech_provider = None
        _tts_provider = None
        _achievement_system = None
        _vector_store = None
        _startup_state = {
            "initialized": False,
            "initializing": False,
            "providers_ready": {
                "speech": False,
                "tts": False,
                "llm": False,
                "achievement": False,
                "vector_store": False,
            },
            "errors": [],
            "startup_time_ms": 0,
        }

    logger.info("All providers reset")
