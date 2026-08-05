import importlib.util
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from src import config
from src.aac_app.models import User
from src.api.deps import (
    get_current_active_user,
    get_current_admin_user,
    get_lmstudio_provider,
    get_ollama_provider,
    get_openrouter_provider,
)
from src.api.deps import providers as provider_deps

router = APIRouter(prefix="/api/providers", tags=["providers"])
_voice_install_lock = threading.Lock()


@router.get("/health")
def providers_health(current_user: User = Depends(get_current_active_user)):
    ollama = get_ollama_provider()
    openrouter = get_openrouter_provider()
    lmstudio = get_lmstudio_provider()
    return {
        "ollama": {
            "available": ollama.is_available(),
            "configured": bool(getattr(ollama, "base_url", "")),
            "reason": None,
        },
        "openrouter": {
            "available": openrouter.is_available(),
            "configured": openrouter.is_configured(),
            "reason": None if openrouter.is_configured() else "api_key_missing",
        },
        "lmstudio": {
            "available": lmstudio.is_available(),
            "configured": lmstudio.is_configured(),
            "reason": None if lmstudio.is_configured() else "base_url_missing",
        },
    }


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _executable_available(name: str) -> bool:
    return shutil.which(name) is not None


def _uv_command() -> str | None:
    """Return a usable uv executable path on Windows source checkouts."""
    candidates = [
        shutil.which("uv"),
        shutil.which("uv.exe"),
        str(Path.home() / ".local" / "bin" / "uv.exe"),
        str(Path.home() / "AppData" / "Local" / "Programs" / "uv" / "uv.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _voice_auto_install_support() -> tuple[bool, str | None]:
    """Return whether this runtime can install the optional voice extra."""
    if sys.platform != "win32":
        return False, "Automatic voice installation is currently supported only on Windows."
    if config.IS_FROZEN:
        return (
            False,
            "The packaged Windows app cannot modify Python extras at runtime.",
        )
    if not (config.PROJECT_ROOT / "pyproject.toml").is_file():
        return False, "Automatic voice installation requires a source checkout."
    if _uv_command() is None:
        return False, "uv is not available on PATH for automatic installation."
    return True, None


@router.get("/voice-status")
def voice_status(current_user: User = Depends(get_current_active_user)):
    """
    Report local STT status and browser-side TTS capability.

    faster-whisper uses PyAV to decode WAV/WebM uploads, so ffmpeg and the
    old server-side microphone packages are not runtime requirements.
    """
    stt_installed = _module_available("faster_whisper")
    ffmpeg_installed = _executable_available("ffmpeg")
    auto_install_supported, auto_install_reason = _voice_auto_install_support()
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
        "actions": {
            "install_voice": {
                "supported": auto_install_supported,
                "in_progress": _voice_install_lock.locked(),
                "reason": auto_install_reason,
                "platform": sys.platform,
            }
        },
    }


@router.post("/voice/install")
def install_voice_dependencies(
    current_user: User = Depends(get_current_admin_user),
):
    """Install the optional faster-whisper voice extra on Windows source checkouts."""
    auto_install_supported, auto_install_reason = _voice_auto_install_support()
    if not auto_install_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=auto_install_reason or "Automatic voice installation is unavailable.",
        )

    if _module_available("faster_whisper"):
        return {
            "success": True,
            "installed": True,
            "message": "Voice dependencies are already installed.",
        }

    if not _voice_install_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A voice dependency installation is already in progress.",
        )

    uv_command = _uv_command()
    if uv_command is None:
        _voice_install_lock.release()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uv is not available on PATH for automatic installation.",
        )

    try:
        logger.info(
            "Admin {} requested automatic faster-whisper installation",
            current_user.username,
        )
        subprocess.run(
            [uv_command, "sync", "--extra", "voice"],
            cwd=config.PROJECT_ROOT,
            check=True,
        )
        provider_deps.reset_providers()
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Automatic voice dependency installation failed with exit code {}",
            exc.returncode,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Automatic voice installation failed. Check the server logs for details.",
        ) from exc
    finally:
        _voice_install_lock.release()

    return {
        "success": True,
        "installed": _module_available("faster_whisper"),
        "message": "Voice dependencies installed successfully.",
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
