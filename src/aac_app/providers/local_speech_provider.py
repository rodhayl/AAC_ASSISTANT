import threading
from pathlib import Path
from typing import Any

from loguru import logger

from ... import config
from ..utils.module_availability import module_available
from ..utils.runtime import safe_streams

# Keep startup checks cheap. faster-whisper and its PyAV/CTranslate2 stack are
# imported only when the first transcription or explicit warmup is requested.
# Checking the native dependencies too prevents a partial installation from
# being advertised as available before the lazy import can actually work.

def is_faster_whisper_available() -> bool:
    """Return whether the complete optional voice stack is installed."""
    return all(
        module_available(module_name)
        for module_name in ("faster_whisper", "ctranslate2", "av")
    )


FASTER_WHISPER_AVAILABLE = is_faster_whisper_available()
faster_whisper = None

DEFAULT_STT_MODEL = "tiny"
SUPPORTED_STT_MODELS: dict[str, dict[str, str]] = {
    "tiny": {"size": "~39M parameters / ~75MB", "description": "Fastest, lowest memory use"},
    "base": {"size": "~74M parameters / ~145MB", "description": "Fast with improved accuracy"},
    "small": {"size": "~244M parameters / ~465MB", "description": "Balanced accuracy and speed"},
    "medium": {"size": "~769M parameters / ~1.5GB", "description": "Higher accuracy, slower"},
    "large-v3": {"size": "~1.55B parameters / ~3GB", "description": "Highest accuracy, slowest"},
}


def normalize_stt_model(model_size: str | None) -> str:
    """Return a supported faster-whisper model, defaulting safely to tiny."""
    candidate = (model_size or DEFAULT_STT_MODEL).strip().lower()
    return candidate if candidate in SUPPORTED_STT_MODELS else DEFAULT_STT_MODEL


class LocalSpeechProvider:
    """Local speech-to-text backed by faster-whisper.

    The provider accepts paths to browser-uploaded WAV/WebM files. PyAV, used
    by faster-whisper, decodes those containers directly, so no ffmpeg process
    or server-side microphone dependency is needed.
    """

    def __init__(
        self,
        model_size: str = DEFAULT_STT_MODEL,
        device: str = "cpu",
        compute_type: str = "int8",
        lazy_load: bool = True,
        model_cache_dir: str | Path | None = None,
    ):
        self.model_size = normalize_stt_model(model_size)
        self.device = device
        self.compute_type = compute_type
        if model_cache_dir is not None:
            self.model_cache_dir = Path(model_cache_dir).absolute()
            self._local_files_only = False
        else:
            resolved, self._local_files_only = config.resolve_model_cache_dir(
                f"models--Systran--faster-whisper-{self.model_size}"
            )
            self.model_cache_dir = Path(resolved).absolute()
        if not self._local_files_only:
            self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.model: Any | None = None
        self._model_loaded = False
        self._load_lock = threading.Lock()
        # faster-whisper's native model is not assumed thread-safe; serializing
        # CPU transcriptions also bounds concurrent memory use on low-end hosts.
        self._model_use_lock = threading.Lock()
        self._load_attempted = False

        if not FASTER_WHISPER_AVAILABLE:
            logger.warning("faster-whisper not available. Speech recognition disabled.")
            self._load_attempted = True
            self._model_loaded = True
        elif not lazy_load:
            self._load_model()

    def _load_faster_whisper(self) -> bool:
        """Import faster-whisper only when transcription is requested."""
        global FASTER_WHISPER_AVAILABLE, faster_whisper
        if faster_whisper is not None:
            return True
        if not FASTER_WHISPER_AVAILABLE:
            return False

        try:
            import faster_whisper as faster_whisper_module

            faster_whisper = faster_whisper_module
            return True
        except ImportError as exc:
            FASTER_WHISPER_AVAILABLE = False
            logger.warning("faster-whisper could not be imported: {}", exc)
            return False

    def _load_model(self) -> None:
        """Load the CTranslate2 model once, leaving startup lazy."""
        # The attempted flag is deliberately checked while holding the same
        # lock used by first-use loading. Without this, a second request can
        # observe ``_load_attempted`` while the first request is still inside
        # WhisperModel(), then incorrectly return an empty transcription.
        with self._load_lock:
            if self._load_attempted:
                return

            self._load_attempted = True

            if not self._load_faster_whisper():
                return

            try:
                logger.info(
                    "Loading faster-whisper model {} on {} ({}) from {}",
                    self.model_size,
                    self.device,
                    self.compute_type,
                    self.model_cache_dir,
                )
                # Windowed frozen builds expose None stdio; faster-whisper's
                # CTranslate2/huggingface_hub stack can still write progress
                # during a lazy load. Wrap it so an on-demand download cannot
                # crash the transcription path.
                with safe_streams():
                    self.model = faster_whisper.WhisperModel(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type,
                        download_root=str(self.model_cache_dir),
                        local_files_only=self._local_files_only,
                    )
                self._model_loaded = True
                logger.info("faster-whisper model loaded successfully")
            except Exception as exc:
                self.model = None
                # A transient failure (interrupted download, low disk space,
                # temporary native error) must not latch STT off until the
                # provider is reset. Clear the attempt flag so the next
                # request can retry while the lock still serializes loads.
                self._load_attempted = False
                logger.error("Failed to load faster-whisper model: {}", exc)


    def _ensure_model_loaded(self) -> None:
        """Load the model on first use."""
        if self.model is None:
            # _load_model() owns the attempted check and lock. Calling it even
            # after another thread marked the attempt lets concurrent callers
            # wait for the in-flight load instead of returning prematurely.
            self._load_model()

    def recognize_from_file(self, audio_path: str, language: str = "en") -> str:
        """Transcribe a WAV/WebM audio file, returning an empty string on failure."""
        if not self.is_available():
            logger.warning("Speech recognition unavailable: install the voice extra")
            return ""

        # Hold the use lock through lazy loading and transcription so release()
        # cannot detach the model between those two operations.
        with self._model_use_lock:
            self._ensure_model_loaded()
            if self.model is None:
                logger.error("Speech recognition unavailable: model failed to load")
                return ""

            try:
                logger.info("Transcribing audio file: {}", audio_path)
                segments, _info = self.model.transcribe(
                    audio_path,
                    language=language,
                    vad_filter=True,
                )
                text = " ".join(
                    segment.text.strip()
                    for segment in segments
                    if getattr(segment, "text", "").strip()
                ).strip()
                logger.info("Transcription result: {}", text)
                return text
            except Exception as exc:
                logger.warning("Transcription failed for {}: {}", audio_path, exc)
                return ""

    def transcribe(self, audio_path: str, language: str = "en") -> str:
        """Compatibility alias for callers using the provider's generic verb."""
        return self.recognize_from_file(audio_path, language=language)

    def get_available_models(self) -> dict[str, dict[str, str]]:
        """Return the supported faster-whisper model sizes."""
        return SUPPORTED_STT_MODELS.copy()

    def is_available(self) -> bool:
        """Return whether the optional faster-whisper package is installed."""
        return FASTER_WHISPER_AVAILABLE

    def is_ready(self) -> bool:
        """Return whether the model has loaded successfully."""
        return self._model_loaded and self.model is not None

    def force_load(self) -> None:
        """Explicitly load the model, useful for warmup or offline preparation."""
        self._ensure_model_loaded()

    def release(self) -> None:
        """Release the loaded model and its native memory, if supported."""
        # Do not close a native model while a request is using it. Settings
        # changes can replace the singleton while an older request is active.
        with self._model_use_lock, self._load_lock:
            model = self.model
            self.model = None
            self._model_loaded = False
            self._load_attempted = False
            if model is not None:
                for method_name in ("unload_model", "close"):
                    method = getattr(model, method_name, None)
                    if callable(method):
                        try:
                            method()
                        except Exception as exc:
                            logger.debug("Speech model release hook failed: {}", exc)
                        break
