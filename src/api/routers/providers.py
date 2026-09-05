import asyncio
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
    is_faster_whisper_available,
    normalize_stt_model,
    refresh_faster_whisper_availability,
)
from src.aac_app.providers.local_tts_provider import (
    get_local_tts_provider,
    kokoro_import_error,
    list_kokoro_voices,
    model_files_present,
)
from src.aac_app.services.local_vector_store import vector_store_operation_lock
from src.api.deps import (
    get_current_active_user,
    get_current_admin_user,
    get_db,
    get_groq_provider,
    get_lmstudio_provider,
    get_ollama_provider,
    get_openrouter_provider,
    get_setting_value,
    get_text,
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
    groq = get_groq_provider()
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
        "groq": {
            "available": groq.is_available(),
            "configured": groq.is_configured(),
            "reason": None if groq.is_configured() else "api_key_missing",
        },
    }


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


def _voice_auto_install_support(user: User | None = None) -> tuple[bool, str | None]:
    """Return whether this runtime can install the optional voice extra."""
    if sys.platform != "win32":
        return False, get_text(
            user=user, key="errors.providers.voiceInstallWindowsOnly"
        )
    if config.IS_FROZEN:
        return (
            False,
            get_text(user=user, key="errors.providers.voiceInstallFrozen"),
        )
    if not (config.PROJECT_ROOT / "pyproject.toml").is_file():
        return False, get_text(
            user=user, key="errors.providers.voiceInstallSourceOnly"
        )
    if _uv_command() is None:
        return False, get_text(user=user, key="errors.providers.uvUnavailable")
    return True, None


@router.get("/voice-status")
def voice_status(current_user: User = Depends(get_current_active_user)):
    """
    Report local STT status and browser-side TTS capability.

    faster-whisper uses PyAV to decode WAV/WebM uploads, so ffmpeg and the
    old server-side microphone packages are not runtime requirements.
    """
    stt_installed = is_faster_whisper_available()
    configured_stt_model = normalize_stt_model(get_setting_value("stt_model", DEFAULT_STT_MODEL))
    ffmpeg_installed = _executable_available("ffmpeg")
    auto_install_supported, auto_install_reason = _voice_auto_install_support(current_user)
    return {
        "stt": {
            "provider": "faster-whisper",
            "installed": stt_installed,
            "available": stt_installed,
            "model_loaded": provider_deps.get_speech_provider().is_ready(),
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
            "model_loaded": get_local_tts_provider().is_ready(),
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
                "message": get_text(
                    user=current_user, key="errors.providers.unsupportedSttModel"
                ),
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

    Returns a 16-bit mono WAV. When the engine or its model files are missing
    this returns 503 so the selected Kokoro provider can report a clear error.
    """
    provider = get_local_tts_provider()
    if not provider.is_available():
        if not provider.is_installed():
            detail = get_text(user=current_user, key="errors.providers.ttsNotInstalled")
        elif not model_files_present():
            detail = get_text(user=current_user, key="errors.providers.ttsModelMissing")
        else:
            detail = get_text(user=current_user, key="errors.providers.ttsUnavailable")
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
            detail=get_text(user=current_user, key="errors.providers.ttsSynthesisFailed"),
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


class WarmupRequest(BaseModel):
    """Select which lazy local models to pre-load. Defaults to all targets."""

    targets: list[str] = Field(
        default_factory=lambda: ["tts", "speech", "vector"],
        description=(
            "Models to pre-load: 'tts' (Kokoro), 'speech' (faster-whisper), "
            "and/or 'vector' (fastembed semantic index)"
        ),
    )


@router.post("/warmup")
def warmup_models(
    payload: WarmupRequest | None = None,
    current_user: User = Depends(get_current_active_user),
):
    """Pre-load every lazy local model in one batched request.

    Kokoro (TTS), faster-whisper (STT), and the fastembed semantic index all
    load lazily on first use; the frontend calls this endpoint in the
    background when the app opens so the first spoken message, the first
    microphone answer, and the first semantic symbol search do not pay the
    model-load cost. Each target runs independently — an unavailable or
    failing target reports ``warmed: False`` (plus an ``error``) without
    affecting the others. The sync endpoint occupies a worker thread (not the
    event loop) while models load, and it stays out of server startup.
    """
    targets = payload.targets if payload is not None else ["tts", "speech", "vector"]
    results: dict[str, dict[str, object]] = {}

    if "tts" in targets:
        try:
            provider = get_local_tts_provider()
            if not provider.is_available():
                results["tts"] = {"warmed": False}
            else:
                provider.warmup()
                results["tts"] = {"warmed": True}
        except Exception as exc:
            logger.warning("TTS warmup failed: {}", exc)
            results["tts"] = {"warmed": False, "error": str(exc)}

    if "speech" in targets:
        try:
            if not is_faster_whisper_available():
                results["speech"] = {"warmed": False}
            else:
                provider_deps.get_speech_provider().force_load()
                results["speech"] = {"warmed": True}
        except Exception as exc:
            logger.warning("Speech warmup failed: {}", exc)
            results["speech"] = {"warmed": False, "error": str(exc)}

    if "vector" in targets:
        try:
            store = provider_deps.get_vector_store()
            if not store.is_available():
                results["vector"] = {"warmed": False}
            else:
                # Serialize against resets: a concurrent provider reset must
                # not close the store while the embedding model is loading.
                with vector_store_operation_lock:
                    store.force_load()
                results["vector"] = {"warmed": store.is_ready()}
        except Exception as exc:
            logger.warning("Vector store warmup failed: {}", exc)
            results["vector"] = {"warmed": False, "error": str(exc)}

    return results


@router.post("/tts/install")
def install_tts_dependencies(
    current_user: User = Depends(get_current_admin_user),
):
    """Install the optional kokoro-onnx extra and download its model files."""
    auto_install_supported, auto_install_reason = _voice_auto_install_support(current_user)
    if not auto_install_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=auto_install_reason
            or get_text(user=current_user, key="errors.providers.ttsInstallUnavailable"),
        )

    if not _tts_download_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=get_text(user=current_user, key="errors.providers.ttsInstallInProgress"),
        )

    uv_command = _uv_command()
    if uv_command is None:
        _tts_download_lock.release()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(user=current_user, key="errors.providers.uvUnavailable"),
        )
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
        reset_local_tts_provider(clear_import_state=True)
    except subprocess.CalledProcessError as exc:
        logger.error("TTS dependency installation failed with exit code {}", exc.returncode)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(user=current_user, key="errors.providers.ttsInstallFailed"),
        ) from exc
    except Exception as exc:
        logger.error("TTS installation failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                user=current_user,
                key="errors.providers.ttsInstallFailedWithError",
            ),
        ) from exc
    finally:
        _tts_download_lock.release()

    return {
        "success": True,
        "installed": get_local_tts_provider().is_available(),
        "message": get_text(user=current_user, key="errors.providers.ttsInstalled"),
    }


@router.post("/voice/install")
def install_voice_dependencies(
    current_user: User = Depends(get_current_admin_user),
):
    """Install the optional faster-whisper voice extra on Windows source checkouts."""
    auto_install_supported, auto_install_reason = _voice_auto_install_support(current_user)
    if not auto_install_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=auto_install_reason
            or get_text(
                user=current_user,
                key="errors.providers.voiceInstallUnavailable",
            ),
        )

    if is_faster_whisper_available():
        return {
            "success": True,
            "installed": True,
            "message": get_text(
                user=current_user, key="errors.providers.voiceAlreadyInstalled"
            ),
        }

    if not _voice_install_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=get_text(
                user=current_user, key="errors.providers.voiceInstallInProgress"
            ),
        )

    uv_command = _uv_command()
    if uv_command is None:
        _voice_install_lock.release()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(user=current_user, key="errors.providers.uvUnavailable"),
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
        refresh_faster_whisper_availability()
        provider_deps.reset_providers()
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Automatic voice dependency installation failed with exit code {}",
            exc.returncode,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(user=current_user, key="errors.providers.voiceInstallFailed"),
        ) from exc
    finally:
        _voice_install_lock.release()

    return {
        "success": True,
        "installed": is_faster_whisper_available(),
        "message": get_text(user=current_user, key="errors.providers.voiceInstalled"),
    }


@router.get("/ai/models/lmstudio")
async def get_lmstudio_models(
    current_user: User = Depends(get_current_active_user),
):
    """Fetch available LM Studio models"""
    try:
        provider = get_lmstudio_provider()
        if not await asyncio.to_thread(provider.is_available):
            return {"models": [], "error": "LM Studio is not available"}

        models_response = await provider.get_available_models()
        models_list = models_response.get("data", [])
        return {"models": models_list}
    except Exception as e:
        return {"models": [], "error": str(e)}
