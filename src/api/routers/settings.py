"""Settings API router for admin configuration"""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import AppSettings, User, UserSettings
from src.aac_app.providers.lmstudio_provider import LMStudioProvider
from src.aac_app.providers.ollama_provider import OllamaProvider
from src.aac_app.providers.openrouter_provider import OpenRouterProvider
from src.api.deps import (
    clear_settings_cache,
    get_current_active_user,
    get_current_admin_user,
    get_db,
    get_text,
    invalidate_setting,
)
from src.api.deps import providers as provider_deps
from src.api.routers.auth_helpers import update_user_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


# Helper functions
def get_setting(db: Session, key: str) -> str | None:
    """Get a setting value by key."""
    return _get_settings(db, (key,)).get(key)


def _get_settings(db: Session, keys: tuple[str, ...]) -> dict[str, str]:
    """Load several settings with one query instead of one query per key."""
    if not keys:
        return {}
    rows = (
        db.query(AppSettings.setting_key, AppSettings.setting_value)
        .filter(AppSettings.setting_key.in_(keys))
        .all()
    )
    return {key: value for key, value in rows if value is not None}


def set_settings(db: Session, values: dict[str, str], user_id: int) -> None:
    """Apply a group of settings atomically, invalidating each changed key."""
    if not values:
        return
    existing = {
        setting.setting_key: setting
        for setting in db.query(AppSettings)
        .filter(AppSettings.setting_key.in_(tuple(values)))
        .all()
    }
    for key, value in values.items():
        setting = existing.get(key)
        if setting is None:
            db.add(AppSettings(setting_key=key, setting_value=value, updated_by=user_id))
        else:
            setting.setting_value = value
            setting.updated_by = user_id
        invalidate_setting(key)


async def _close_provider(provider: Any | None) -> None:
    """Best-effort cleanup for short-lived provider clients used by settings."""
    if provider is None:
        return
    close_async = getattr(provider, "close_async", None)
    close = getattr(provider, "close", None)
    close_method = close_async if callable(close_async) else close
    if not callable(close_method):
        return
    try:
        result = close_method()
        if hasattr(result, "__await__"):
            await result
    except Exception as exc:
        logger.debug("Provider cleanup failed after settings request: {}", exc)


# Endpoints
@router.get("/ai")
def get_ai_settings(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """Get current AI provider settings (all users can view, sensitive data masked for non-admins)"""
    values = _get_settings(
        db,
        (
            "ai_provider",
            "ollama_model",
            "openrouter_model",
            "openrouter_api_key",
            "ollama_base_url",
            "lmstudio_base_url",
            "lmstudio_model",
            "ai_max_tokens",
            "ai_temperature",
        ),
    )
    provider = values.get("ai_provider") or "ollama"
    ollama_model = values.get("ollama_model") or ""
    openrouter_model = values.get("openrouter_model") or ""
    openrouter_api_key = values.get("openrouter_api_key") or ""
    ollama_base_url = values.get("ollama_base_url") or config.OLLAMA_BASE_URL
    lmstudio_base_url = values.get("lmstudio_base_url") or "http://localhost:1234/v1"
    lmstudio_model = values.get("lmstudio_model") or ""
    max_tokens = values.get("ai_max_tokens") or "1024"
    temperature = values.get("ai_temperature") or "0.5"

    # Mask API key for non-admins or even for admins (usually only show last few chars or empty)
    # If admin, show full key? Or maybe better to just show it's set.
    # For now, if admin, return it. If not, mask it.
    if current_user.user_type != "admin":
        openrouter_api_key = (
            "********" if openrouter_api_key else None
        )

    return {
        "provider": provider,
        "ollama_model": ollama_model,
        "openrouter_model": openrouter_model,
        "openrouter_api_key": openrouter_api_key,
        "ollama_base_url": ollama_base_url,
        "lmstudio_base_url": lmstudio_base_url,
        "lmstudio_model": lmstudio_model,
        "max_tokens": int(max_tokens) if max_tokens is not None else 1024,
        "temperature": float(temperature) if temperature is not None else 0.5,
        "can_edit": current_user.user_type == "admin",
    }


@router.put("/ai")
def update_ai_settings(
    settings: dict[str, Any],
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Update AI provider settings (admin only)"""
    # Validate provider
    provider = settings.get("provider")
    if provider not in ["ollama", "openrouter", "lmstudio"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(
                key="errors.provider.invalid",
                accept_language=(
                    current_user.settings.ui_language if current_user.settings else None
                ),
            ),
        )

    # Collect all changes before writing them in one query-backed update. This
    # keeps the request atomic and avoids one SELECT per setting key.
    updated_values: dict[str, str] = {
        key: settings[key]
        for key in (
            "provider",
            "ollama_model",
            "openrouter_model",
            "openrouter_api_key",
            "ollama_base_url",
            "lmstudio_base_url",
            "lmstudio_model",
        )
        if key in settings
    }
    if "provider" in updated_values:
        updated_values["ai_provider"] = updated_values.pop("provider")

    # Optional: global LLM behavior controls
    if "max_tokens" in settings and settings["max_tokens"] is not None:
        try:
            value = int(settings["max_tokens"])
            if value <= 0:
                raise ValueError
            updated_values["ai_max_tokens"] = str(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=get_text(
                    key="errors.settings.maxTokensPositive",
                    accept_language=(
                        current_user.settings.ui_language
                        if current_user.settings
                        else None
                    ),
                ),
            )

    if "temperature" in settings and settings["temperature"] is not None:
        try:
            value = float(settings["temperature"])
            if not (0.0 <= value <= 1.5):
                raise ValueError
            updated_values["ai_temperature"] = str(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=get_text(
                    key="errors.settings.temperatureRange",
                    accept_language=(
                        current_user.settings.ui_language
                        if current_user.settings
                        else None
                    ),
                ),
            )

    # Mask API key in log
    log_settings = settings.copy()
    if "openrouter_api_key" in log_settings:
        log_settings["openrouter_api_key"] = "********"

    set_settings(db, updated_values, current_user.id)
    logger.info(f"Admin {current_user.username} updated AI settings: {log_settings}")
    # Make the new values durable before the provider singletons are rebuilt:
    # the request dependency's teardown commit runs after the response is
    # sent, so a follow-up request that lazily constructs a provider could
    # otherwise read the previous settings from the database.
    db.commit()
    provider_deps.reset_llm_providers()

    return {"message": "Settings updated successfully", "settings": settings}


@router.get("/ai/models/ollama")
async def get_ollama_models(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Fetch available Ollama models (admin only)"""
    provider: OllamaProvider | None = None
    try:
        base_url = get_setting(db, "ollama_base_url") or config.OLLAMA_BASE_URL
        provider = OllamaProvider(base_url=base_url)

        if not await asyncio.to_thread(provider.is_available):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=get_text(
                    key="errors.provider.unavailable",
                    accept_language=(
                        current_user.settings.ui_language
                        if current_user.settings
                        else None
                    ),
                ),
            )

        model_names = await asyncio.to_thread(provider.list_models)
        # Convert to format expected by frontend
        models = [{"name": name} for name in model_names]
        return {"models": models, "base_url": base_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Ollama models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                key="errors.provider.fetchModelsFailed",
                error=str(e),
                accept_language=(
                    current_user.settings.ui_language if current_user.settings else None
                ),
            ),
        )
    finally:
        await _close_provider(provider)


@router.get("/ai/models/openrouter")
async def get_openrouter_models(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    request_api_key: str | None = Header(default=None, alias="X-OpenRouter-API-Key"),
):
    """Fetch available OpenRouter models (admin only)"""
    provider: OpenRouterProvider | None = None
    try:
        # The settings form may contain a newly entered key that has not been
        # saved yet. Prefer that request-scoped value, while preserving the
        # saved setting as the fallback for automatic refreshes.
        api_key = request_api_key.strip() if request_api_key else None
        api_key = api_key or get_setting(db, "openrouter_api_key")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=get_text(
                    key="errors.provider.openRouterKeyMissing",
                    accept_language=(
                        current_user.settings.ui_language
                        if current_user.settings
                        else None
                    ),
                ),
            )

        provider = OpenRouterProvider(api_key=api_key)
        models_response = await provider.get_available_models()

        # Parse the response - OpenRouter returns {"data": [models]}
        models_list = models_response.get("data", [])

        return {"models": models_list}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching OpenRouter models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                key="errors.provider.fetchOpenRouterModelsFailed",
                error=str(e),
                accept_language=(
                    current_user.settings.ui_language if current_user.settings else None
                ),
            ),
        )
    finally:
        await _close_provider(provider)


@router.get("/ai/models/lmstudio")
async def get_lmstudio_models(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Fetch available LM Studio models (admin only)"""
    provider: LMStudioProvider | None = None
    try:
        base_url = get_setting(db, "lmstudio_base_url") or "http://localhost:1234/v1"
        provider = LMStudioProvider(base_url=base_url)

        if not await asyncio.to_thread(provider.is_available):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=get_text(
                    key="errors.provider.unavailable",
                    accept_language=(
                        current_user.settings.ui_language
                        if current_user.settings
                        else None
                    ),
                ),
            )

        models_response = await provider.get_available_models()
        models_list = models_response.get("data", [])
        return {"models": models_list, "base_url": base_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching LM Studio models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                key="errors.provider.fetchModelsFailed",
                error=str(e),
                accept_language=(
                    current_user.settings.ui_language if current_user.settings else None
                ),
            ),
        )
    finally:
        await _close_provider(provider)


# UI Language endpoints
@router.get("/ui")
def get_ui_language(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    settings = (
        db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    )
    ui_lang = settings.ui_language if settings else "es"
    return {"ui_language": ui_lang}


@router.put("/ui")
def update_ui_language(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    lang = (payload or {}).get("ui_language")
    if lang not in ["es", "en", "es-ES", "en-US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(
                key="errors.settings.unsupportedLanguage",
                accept_language=(
                    current_user.settings.ui_language if current_user.settings else None
                ),
            ),
        )
    settings = update_user_settings(
        db,
        current_user.id,
        {"ui_language": lang},
    )
    db.commit()
    db.refresh(settings)
    clear_settings_cache()
    logger.info(f"User {current_user.username} updated UI language to {lang}")
    return {"message": "UI language updated", "ui_language": settings.ui_language}
