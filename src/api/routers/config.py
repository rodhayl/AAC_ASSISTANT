"""Configuration API router - exposes config to frontend."""

from fastapi import APIRouter

from src import config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config():
    """Get frontend-relevant configuration values."""
    return {
        "backend_port": config.BACKEND_PORT,
        "frontend_port": config.FRONTEND_PORT,
        "ollama_base_url": config.OLLAMA_BASE_URL,
        "app_name": config.APP_NAME,
        "app_version": config.APP_VERSION,
        "default_locale": config.DEFAULT_LOCALE,
    }
