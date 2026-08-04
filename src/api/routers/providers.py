import importlib.util
import shutil

from fastapi import APIRouter, Depends

from src.aac_app.models import User
from src.api.deps import (
    get_current_active_user,
    get_lmstudio_provider,
    get_ollama_provider,
    get_openrouter_provider,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/health")
def providers_health(current_user: User = Depends(get_current_active_user)):
    ollama = get_ollama_provider()
    openrouter = get_openrouter_provider()
    lmstudio = get_lmstudio_provider()
    return {
        "ollama": {"available": ollama.is_available()},
        "openrouter": {"available": openrouter.is_available()},
        "lmstudio": {"available": lmstudio.is_available()},
    }


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _executable_available(name: str) -> bool:
    return shutil.which(name) is not None


@router.get("/voice-status")
def voice_status(current_user: User = Depends(get_current_active_user)):
    """
    Report local STT status and browser-side TTS capability.

    faster-whisper uses PyAV to decode WAV/WebM uploads, so ffmpeg and the
    old server-side microphone packages are not runtime requirements.
    """
    stt_installed = _module_available("faster_whisper")
    ffmpeg_installed = _executable_available("ffmpeg")
    return {
        "stt": {
            "provider": "faster-whisper",
            "installed": stt_installed,
            "available": stt_installed,
            "model": "small",
        },
        # Keep the old key as a response-shape compatibility alias for clients
        # that have not yet switched their settings panel to `stt`.
        "whisper": {
            "provider": "faster-whisper",
            "installed": stt_installed,
            "available": stt_installed,
        },
        "ffmpeg": {
            "installed": ffmpeg_installed,
            "available": ffmpeg_installed,
            "required": False,
        },
        "tts": {
            "provider": "browser",
            "client_side": True,
            "installed": True,
            "available": True,
        },
    }


@router.get("/ai/models/lmstudio")
async def get_lmstudio_models(
    current_user: User = Depends(get_current_active_user),
):
    """Fetch available LM Studio models"""
    try:
        provider = get_lmstudio_provider()
        if not provider.is_available():
             pass

        models_response = await provider.get_available_models()
        models_list = models_response.get("data", [])
        return {"models": models_list}
    except Exception as e:
        return {"models": [], "error": str(e)}
