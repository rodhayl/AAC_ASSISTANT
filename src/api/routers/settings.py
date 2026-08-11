"""Settings API router for admin configuration"""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter(prefix="/api/settings", tags=["settings"])


# Helper functions
def get_setting(db: Session, key: str) -> str | None:
    """Get a setting value by key"""
    setting = db.query(AppSettings).filter(AppSettings.setting_key == key).first()
    return setting.setting_value if setting else None


def set_setting(db: Session, key: str, value: str, user_id: int):
    """Set or update a setting value"""
    setting = db.query(AppSettings).filter(AppSettings.setting_key == key).first()
    if setting:
        setting.setting_value = value
        setting.updated_by = user_id
    else:
        setting = AppSettings(setting_key=key, setting_value=value, updated_by=user_id)
        db.add(setting)
    # Keep the whole settings request in the transaction owned by get_db().
    # Committing here would make earlier keys durable if a later validation
    # fails, leaving a partially applied configuration.
    invalidate_setting(key)
    return setting


async def _close_provider(provider: Any | None) -> None:
    """Best-effort cleanup for short-lived provider clients used by settings."""
    if provider is None:
        return
    close_async = getattr(provider, "close_async", None)
    if not callable(close_async):
        return
    try:
        await close_async()
    except Exception as exc:
        logger.debug("Provider cleanup failed after settings request: {}", exc)


# Endpoints
@router.get("/ai")
async def get_ai_settings(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """Get current AI provider settings (all users can view, sensitive data masked for non-admins)"""
    provider = get_setting(db, "ai_provider") or "ollama"
    ollama_model = get_setting(db, "ollama_model") or ""
    openrouter_model = get_setting(db, "openrouter_model") or ""
    openrouter_api_key = get_setting(db, "openrouter_api_key") or ""
    ollama_base_url = get_setting(db, "ollama_base_url") or config.OLLAMA_BASE_URL
    lmstudio_base_url = get_setting(db, "lmstudio_base_url") or "http://localhost:1234/v1"
    lmstudio_model = get_setting(db, "lmstudio_model") or ""
    # LLM behavior tuning
    max_tokens = get_setting(db, "ai_max_tokens") or "1024"
    temperature = get_setting(db, "ai_temperature") or "0.5"

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
async def update_ai_settings(
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

    # Update settings
    if "provider" in settings:
        set_setting(db, "ai_provider", settings["provider"], current_user.id)

    if "ollama_model" in settings:
        set_setting(db, "ollama_model", settings["ollama_model"], current_user.id)

    if "openrouter_model" in settings:
        set_setting(
            db, "openrouter_model", settings["openrouter_model"], current_user.id
        )

    if "openrouter_api_key" in settings:
        set_setting(
            db, "openrouter_api_key", settings["openrouter_api_key"], current_user.id
        )

    if "ollama_base_url" in settings:
        set_setting(db, "ollama_base_url", settings["ollama_base_url"], current_user.id)

    if "lmstudio_base_url" in settings:
        set_setting(db, "lmstudio_base_url", settings["lmstudio_base_url"], current_user.id)

    if "lmstudio_model" in settings:
        set_setting(db, "lmstudio_model", settings["lmstudio_model"], current_user.id)

    # Optional: global LLM behavior controls
    if "max_tokens" in settings and settings["max_tokens"] is not None:
        try:
            value = int(settings["max_tokens"])
            if value <= 0:
                raise ValueError
            set_setting(db, "ai_max_tokens", str(value), current_user.id)
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
            set_setting(db, "ai_temperature", str(value), current_user.id)
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

    logger.info(f"Admin {current_user.username} updated AI settings: {log_settings}")
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
):
    """Fetch available OpenRouter models (admin only)"""
    provider: OpenRouterProvider | None = None
    try:
        api_key = get_setting(db, "openrouter_api_key")
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
async def get_ui_language(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    settings = (
        db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    )
    ui_lang = settings.ui_language if settings else "es"
    return {"ui_language": ui_lang}


@router.put("/ui")
async def update_ui_language(
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
    settings = (
        db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    )
    if not settings:
        settings = UserSettings(user_id=current_user.id, ui_language=lang)
        db.add(settings)
    else:
        settings.ui_language = lang
    db.commit()
    db.refresh(settings)
    clear_settings_cache()
    logger.info(f"User {current_user.username} updated UI language to {lang}")
    return {"message": "UI language updated", "ui_language": settings.ui_language}
