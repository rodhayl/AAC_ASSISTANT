import importlib.util
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import AppSettings, User
from src.aac_app.providers.local_speech_provider import (
    DEFAULT_STT_MODEL,
    SUPPORTED_STT_MODELS,
    normalize_stt_model,
)
from src.aac_app.providers.local_tts_provider import (
    get_local_tts_provider,
    kokoro_import_error,
    list_kokoro_voices,
    model_files_present,
)
from src.api.deps import (
    get_current_active_user,
    get_current_admin_user,
    get_db,
    get_lmstudio_provider,
    get_ollama_provider,
    get_openrouter_provider,
    get_setting_value,
    invalidate_setting,
)
from src.api.deps import providers as provider_deps

router = APIRouter(prefix="/api/providers", tags=["providers"])
_voice_install_lock = threading.Lock()
_tts_download_lock = threading.Lock()


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
    configured_stt_model = normalize_stt_model(get_setting_value("stt_model", DEFAULT_STT_MODEL))
    ffmpeg_installed = _executable_available("ffmpeg")
    auto_install_supported, auto_install_reason = _voice_auto_install_support()
    return {
        "stt": {
            "provider": "faster-whisper",
            "installed": stt_installed,
            "available": stt_installed,
            "model": configured_stt_model,
            "models": {
                name: {**details, "selected": name == configured_stt_model}
                for name, details in SUPPORTED_STT_MODELS.items()
            },
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
        "tts_local": {
            "provider": "kokoro",
            "installed": get_local_tts_provider().is_installed(),
            "model_present": model_files_present(),
            "available": get_local_tts_provider().is_available(),
            "model_size_mb": 325,
            "import_error": kokoro_import_error(),
            "download_in_progress": _tts_download_lock.locked(),
            # Specific Kokoro voices (name/language/gender/region) for the
            # per-language voice picker in Settings -> Voice.
            "voices": list_kokoro_voices(),
        },
        "actions": {
            "install_voice": {
                "supported": auto_install_supported,
                "in_progress": _voice_install_lock.locked(),
                "reason": auto_install_reason,
                "platform": sys.platform,
            },
            "install_tts": {
                "supported": auto_install_supported,
                "in_progress": _tts_download_lock.locked(),
                "reason": auto_install_reason,
                "platform": sys.platform,
            },
        },
    }


class STTModelUpdateRequest(BaseModel):
    """Global faster-whisper model selection managed by administrators."""

    model: str = Field(..., description="Supported faster-whisper model size")


@router.put("/stt/model")
def update_stt_model(
    payload: STTModelUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Select the global faster-whisper model used for future transcriptions."""
    requested = (payload.model or "").strip().lower()
    if requested not in SUPPORTED_STT_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Unsupported faster-whisper model.",
                "supported_models": list(SUPPORTED_STT_MODELS),
            },
        )

    setting = db.query(AppSettings).filter(AppSettings.setting_key == "stt_model").first()
    if setting:
        setting.setting_value = requested
        setting.updated_by = current_user.id
    else:
        db.add(
            AppSettings(
                setting_key="stt_model",
                setting_value=requested,
                updated_by=current_user.id,
            )
        )
    db.commit()
    invalidate_setting("stt_model")
    provider_deps.reset_speech_provider()
    logger.info("Admin {} selected STT model {}", current_user.username, requested)
    return {
        "success": True,
        "model": requested,
        "models": SUPPORTED_STT_MODELS,
    }


class TTSSynthesizeRequest(BaseModel):
    """Payload for the local neural TTS synthesizer endpoint."""

    text: str = Field(..., min_length=1, max_length=2000, description="Text to speak")
    lang: str = Field("es", description="Language code, e.g. 'es' or 'en'")
    voice: str = Field(
        "default",
        description="'default', 'female', 'male', or a specific Kokoro voice name "
        "such as 'ef_dora' (a specific voice also selects its language)",
    )
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Speaking rate multiplier")


@router.post("/tts/synthesize")
def tts_synthesize(
    payload: TTSSynthesizeRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Synthesize text with the local neural TTS engine (Kokoro).

    Returns a 16-bit mono WAV. When the optional engine or its model files
    are missing this returns 503 so the frontend can fall back to the
    browser's SpeechSynthesis voices.
    """
    provider = get_local_tts_provider()
    if not provider.is_available():
        detail = "Local neural TTS is not available."
        if not provider.is_installed():
            detail += " Install the 'tts' extra (uv sync --extra tts)."
        elif not model_files_present():
            detail += " The Kokoro model has not been downloaded yet."
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

    wav_bytes = provider.synthesize(
        payload.text,
        lang=payload.lang,
        voice=payload.voice,
        speed=payload.speed,
    )
    if wav_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local neural TTS synthesis failed.",
        )
    logger.info(
        "User {} synthesized {} chars of {} TTS",
        current_user.username,
        len(payload.text),
        payload.lang,
    )
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/tts/install")
def install_tts_dependencies(
    current_user: User = Depends(get_current_admin_user),
):
    """Install the optional kokoro-onnx extra and download its model files."""
    auto_install_supported, auto_install_reason = _voice_auto_install_support()
    if not auto_install_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=auto_install_reason or "Automatic TTS installation is unavailable.",
        )

    if not _tts_download_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A TTS installation is already in progress.",
        )

    uv_command = _uv_command()
    try:
        if not get_local_tts_provider().is_installed():
            logger.info("Admin {} requested kokoro-onnx installation", current_user.username)
            subprocess.run(
                [uv_command, "sync", "--extra", "tts"],
                cwd=config.PROJECT_ROOT,
                check=True,
            )
            provider_deps.reset_providers()

        from src.aac_app.providers.local_tts_provider import (
            download_kokoro_model,
            reset_local_tts_provider,
        )

        if not model_files_present():
            logger.info("Admin {} requested Kokoro model download", current_user.username)
            if not download_kokoro_model():
                raise RuntimeError("Kokoro model download failed")
        reset_local_tts_provider()
    except subprocess.CalledProcessError as exc:
        logger.error("TTS dependency installation failed with exit code {}", exc.returncode)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Automatic TTS installation failed. Check the server logs.",
        ) from exc
    except Exception as exc:
        logger.error("TTS installation failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Automatic TTS installation failed: {exc}",
        ) from exc
    finally:
        _tts_download_lock.release()

    return {
        "success": True,
        "installed": get_local_tts_provider().is_available(),
        "message": "Local neural TTS installed successfully.",
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
