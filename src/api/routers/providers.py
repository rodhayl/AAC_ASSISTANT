import importlib
import shutil

from fastapi import APIRouter, Depends

from src.aac_app.models.database import User
from src.api.dependencies import (
    get_current_active_user,
    get_ollama_provider,
    get_openrouter_provider,
    get_lmstudio_provider,
)
from src.aac_app.providers.lmstudio_provider import LMStudioProvider

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
        importlib.import_module(name)
        return True
    except Exception:
        return False


@router.get("/voice-status")
def voice_status(current_user: User = Depends(get_current_active_user)):
    """
    Report local voice/STT dependency status so the UI can guide setup.

    This is used by the Settings page to show which pieces are installed:
    - ffmpeg: required for Whisper to read most audio formats
    - whisper: Python package providing the STT model
    - sounddevice / soundfile: required for live microphone recording
    - webrtcvad: optional VAD for smarter continuous listening
    """
    ffmpeg_path = shutil.which("ffmpeg")
    return {
        "ffmpeg": {
            "installed": ffmpeg_path is not None,
            "path": ffmpeg_path,
        },
        "whisper": {
            "installed": _module_available("whisper"),
        },
        "sounddevice": {
            "installed": _module_available("sounddevice"),
            # Required only for microphone input, not file uploads
            "optional": False,
        },
        "soundfile": {
            "installed": _module_available("soundfile"),
            # Required only for microphone input, not file uploads
            "optional": False,
        },
        # Optional helpers (informational)
        "webrtcvad": {
            "installed": _module_available("webrtcvad"),
            "optional": True,
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
