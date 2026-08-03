import importlib.util
from pathlib import Path
from typing import Any

from loguru import logger

from ... import config


def _module_available(module_name: str) -> bool:
    """Check whether an optional module exists without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


# Keep startup checks cheap. faster-whisper and its PyAV/CTranslate2 stack are
# imported only when the first transcription or explicit warmup is requested.
FASTER_WHISPER_AVAILABLE = _module_available("faster_whisper")
faster_whisper = None


class LocalSpeechProvider:
    """Local speech-to-text backed by faster-whisper.

    The provider accepts paths to browser-uploaded WAV/WebM files. PyAV, used
    by faster-whisper, decodes those containers directly, so no ffmpeg process
    or server-side microphone dependency is needed.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        lazy_load: bool = True,
        model_cache_dir: str | Path | None = None,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model_cache_dir = Path(
            model_cache_dir or config.get_data_path("models")
        ).absolute()
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.model: Any | None = None
        self._model_loaded = False
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
            self.model = faster_whisper.WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.model_cache_dir),
            )
            self._model_loaded = True
            logger.info("faster-whisper model loaded successfully")
        except Exception as exc:
            self.model = None
            logger.error("Failed to load faster-whisper model: {}", exc)

    def _ensure_model_loaded(self) -> None:
        """Load the model on first use."""
        if self.model is None and not self._load_attempted:
            self._load_model()

    def recognize_from_file(self, audio_path: str, language: str = "en") -> str:
        """Transcribe a WAV/WebM audio file, returning an empty string on failure."""
        if not self.is_available():
            logger.warning("Speech recognition unavailable: install the voice extra")
            return ""

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
        return {
            "tiny": {"size": "75MB", "description": "Fastest, lowest accuracy"},
            "base": {"size": "145MB", "description": "Good balance for speed/accuracy"},
            "small": {"size": "465MB", "description": "Recommended for most use cases"},
            "medium": {"size": "1.5GB", "description": "Better accuracy, slower"},
            "large-v3": {"size": "3GB", "description": "Best accuracy, slowest"},
        }

    def is_available(self) -> bool:
        """Return whether the optional faster-whisper package is installed."""
        return FASTER_WHISPER_AVAILABLE

    def is_ready(self) -> bool:
        """Return whether the model has loaded successfully."""
        return self._model_loaded and self.model is not None

    def force_load(self) -> None:
        """Explicitly load the model, useful for warmup or offline preparation."""
        self._ensure_model_loaded()
