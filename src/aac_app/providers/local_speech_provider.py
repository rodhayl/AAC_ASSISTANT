import importlib.util
import os
import threading
import warnings
from collections.abc import Callable
from queue import Queue

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=".*pkg_resources is deprecated as an API.*",
)

from loguru import logger


def _module_available(module_name: str) -> bool:
    """Check whether an optional module exists without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


# Keep availability checks cheap during startup. The actual imports happen in
# the first method that needs each dependency.
WHISPER_AVAILABLE = _module_available("whisper")
SOUNDDEVICE_AVAILABLE = _module_available("sounddevice")
SOUNDFILE_AVAILABLE = _module_available("soundfile")
NUMPY_AVAILABLE = _module_available("numpy")
WEBRTC_VAD_AVAILABLE = _module_available("webrtcvad")

whisper = None
sd = None
sf = None
np = None
webrtcvad = None


class LocalSpeechProvider:
    """
    100% local speech recognition using OpenAI Whisper.

    Uses LAZY LOADING - Whisper model is only loaded on first transcription request,
    not during initialization. This dramatically improves startup time.
    """

    def __init__(self, model_size: str = "small", device: str = "cpu", lazy_load: bool = True):
        """
        Initialize Whisper provider.

        Models: tiny(39MB), base(74MB), small(244MB), medium(769MB), large(1.5GB)
        Recommended: small (good accuracy/speed balance)

        Args:
            model_size: Whisper model size to use
            device: 'cpu' or 'cuda'
            lazy_load: If True, defer model loading until first use
        """
        self.model_size = model_size
        self.device = device
        self.model = None
        self._model_loaded = False
        self._lazy_load = lazy_load
        self.sample_rate = 16000
        self.audio_queue: Queue = Queue()
        self.is_recording = False
        self.vad = None

        if not WHISPER_AVAILABLE:
            logger.warning("Whisper not available. Speech recognition disabled.")
            self._model_loaded = True  # Mark as attempted
            return

        if not lazy_load:
            # Immediate loading (backwards compatible for warmup)
            self._load_model()

    def _load_whisper(self) -> bool:
        """Import Whisper only when a transcription is requested."""
        global WHISPER_AVAILABLE, whisper
        if whisper is not None:
            return True
        if not WHISPER_AVAILABLE:
            return False
        try:
            import whisper as whisper_module

            whisper = whisper_module
            return True
        except ImportError as e:
            WHISPER_AVAILABLE = False
            if os.getenv("AAC_WARN_ON_OPTIONAL_MISSING") == "1":
                warnings.warn(f"Whisper not available: {e}", stacklevel=2)
            return False

    def _load_audio_dependencies(self, *, include_vad: bool = False) -> bool:
        """Import microphone/VAD dependencies only for microphone features."""
        global NUMPY_AVAILABLE, SOUNDFILE_AVAILABLE, SOUNDDEVICE_AVAILABLE, WEBRTC_VAD_AVAILABLE
        global np, sd, sf, webrtcvad

        if SOUNDDEVICE_AVAILABLE and sd is None:
            try:
                import sounddevice as sounddevice_module

                sd = sounddevice_module
            except ImportError:
                SOUNDDEVICE_AVAILABLE = False
        if SOUNDFILE_AVAILABLE and sf is None:
            try:
                import soundfile as soundfile_module

                sf = soundfile_module
            except ImportError:
                SOUNDFILE_AVAILABLE = False
        if NUMPY_AVAILABLE and np is None:
            try:
                import numpy as numpy_module

                np = numpy_module
            except ImportError:
                NUMPY_AVAILABLE = False
        if include_vad and WEBRTC_VAD_AVAILABLE and webrtcvad is None:
            try:
                import webrtcvad as webrtcvad_module

                webrtcvad = webrtcvad_module
            except ImportError:
                WEBRTC_VAD_AVAILABLE = False

        return SOUNDDEVICE_AVAILABLE and SOUNDFILE_AVAILABLE

    def _ensure_vad(self) -> None:
        """Create the VAD object only when continuous recognition uses it."""
        if self.vad is not None or not WEBRTC_VAD_AVAILABLE:
            return
        self._load_audio_dependencies(include_vad=True)
        if webrtcvad is None:
            return
        try:
            self.vad = webrtcvad.Vad(2)  # Aggressiveness level 0-3
        except Exception as e:
            logger.warning(f"Failed to initialize VAD: {e}")

    def _ensure_model_loaded(self):
        """Ensure Whisper model is loaded (lazy loading)"""
        if self._model_loaded:
            return
        self._load_model()

    def _load_model(self):
        """Load the Whisper model"""
        if self._model_loaded or not WHISPER_AVAILABLE:
            return

        if not self._load_whisper():
            self._model_loaded = True
            return

        try:
            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}")
            self.model = whisper.load_model(self.model_size, device=self.device)
            self._model_loaded = True
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self.model = None
            self._model_loaded = True  # Mark as attempted to avoid retry loops

    def recognize_from_file(self, audio_path: str, language: str = "en") -> str:
        """Transcribe audio file"""
        if not WHISPER_AVAILABLE:
            logger.error("Speech recognition not available - Whisper not installed")
            return ""

        # Lazy load model on first use
        self._ensure_model_loaded()

        if self.model is None:
            logger.error("Speech recognition not available - Whisper model failed to load")
            return ""

        try:
            logger.info(f"Transcribing audio file: {audio_path}")
            result = self.model.transcribe(
                audio_path, language=language, fp16=False  # CPU compatibility
            )
            text = result["text"].strip()
            logger.info(f"Transcription result: {text}")
            return text
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""

    def recognize_from_microphone(self, duration_seconds: int = 5) -> str:
        """Record from mic and transcribe"""
        if not WHISPER_AVAILABLE:
            logger.error("Speech recognition not available - Whisper not installed")
            return ""

        # Lazy load model on first use
        self._ensure_model_loaded()

        if self.model is None:
            logger.error("Speech recognition not available - Whisper model failed to load")
            return ""

        if not (SOUNDDEVICE_AVAILABLE and SOUNDFILE_AVAILABLE):
            logger.error(
                "Microphone recording not available - sounddevice/soundfile missing"
            )
            return ""

        self._load_audio_dependencies()
        if sd is None or sf is None:
            logger.error(
                "Microphone recording not available - sounddevice/soundfile missing"
            )
            return ""

        logger.info(f"Recording from microphone for {duration_seconds} seconds")

        try:
            # Record audio
            audio = sd.rec(
                int(duration_seconds * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
        except Exception as e:
            logger.error(f"Microphone recording failed: {e}")
            return ""

        # Save temporary file
        temp_path = "temp_audio.wav"
        sf.write(temp_path, audio, self.sample_rate)

        # Transcribe
        return self.recognize_from_file(temp_path)

    def _detect_speech(self, audio_data) -> bool:
        """Detect if audio contains speech using WebRTC VAD"""
        if not WHISPER_AVAILABLE or self.vad is None or not NUMPY_AVAILABLE:
            return True  # Assume speech if VAD not available

        self._load_audio_dependencies()
        if np is None:
            return True

        try:
            # Convert to 16-bit PCM for VAD
            audio_int16 = (audio_data * 32767).astype(np.int16)

            # VAD expects 10ms frames at 16kHz (160 samples)
            frame_size = 160
            if len(audio_int16) >= frame_size:
                frame = audio_int16[:frame_size].tobytes()
                return self.vad.is_speech(frame, self.sample_rate)
            return False
        except Exception as e:
            logger.warning(f"VAD detection failed: {e}")
            return True  # Assume speech if VAD fails

    def _process_audio_queue(self, callback: Callable[[str], None]):
        """Process audio queue in background thread"""
        while self.is_recording:
            try:
                # Get audio from queue (timeout to allow checking is_recording)
                audio_data = self.audio_queue.get(timeout=0.1)

                # Save to temporary file
                temp_path = "temp_continuous.wav"
                sf.write(temp_path, audio_data, self.sample_rate)

                # Transcribe
                text = self.recognize_from_file(temp_path)

                if text.strip():
                    callback(text.strip())

            except Exception:
                # Queue empty or timeout, continue loop
                continue

    def start_continuous_recognition(
        self, callback: Callable[[str], None], vad_enabled: bool = True
    ):
        """Continuous listening with voice activity detection"""
        logger.info("Starting continuous speech recognition")

        if not WHISPER_AVAILABLE:
            logger.error("Cannot start continuous recognition - Whisper not installed")
            return None

        # Lazy load model on first use
        self._ensure_model_loaded()

        if self.model is None:
            logger.error("Cannot start continuous recognition - Whisper model failed to load")
            return None

        self._load_audio_dependencies(include_vad=vad_enabled)
        if not (SOUNDDEVICE_AVAILABLE and SOUNDFILE_AVAILABLE) or sd is None or sf is None:
            logger.error(
                "Cannot start continuous recognition - sounddevice/soundfile missing"
            )
            return None

        self.is_recording = True

        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio callback status: {status}")

            if vad_enabled:
                # Use WebRTC VAD to detect speech
                self._ensure_vad()
                is_speech = self._detect_speech(indata[:, 0])
                if is_speech:
                    self.audio_queue.put(indata.copy())
            else:
                self.audio_queue.put(indata.copy())

        # Start audio stream
        try:
            stream = sd.InputStream(
                callback=audio_callback, channels=1, samplerate=self.sample_rate
            )
            stream.start()

            # Process queue in background
            processing_thread = threading.Thread(
                target=self._process_audio_queue, args=(callback,), daemon=True
            )
            processing_thread.start()

            logger.info("Continuous recognition started successfully")
            return stream

        except Exception as e:
            logger.error(f"Failed to start continuous recognition: {e}")
            self.is_recording = False
            return None

    def stop_continuous_recognition(self):
        """Stop continuous recognition"""
        logger.info("Stopping continuous speech recognition")
        self.is_recording = False

    def get_available_models(self) -> dict:
        """Get information about available Whisper models"""
        return {
            "tiny": {"size": "39MB", "description": "Fastest, lowest accuracy"},
            "base": {"size": "74MB", "description": "Good balance for speed/accuracy"},
            "small": {"size": "244MB", "description": "Recommended for most use cases"},
            "medium": {"size": "769MB", "description": "Better accuracy, slower"},
            "large": {"size": "1.5GB", "description": "Best accuracy, slowest"},
        }

    def is_available(self) -> bool:
        """Check if Whisper is available (without loading model)"""
        return WHISPER_AVAILABLE

    def is_ready(self) -> bool:
        """Check if the model is fully loaded and ready"""
        return self._model_loaded and self.model is not None

    def force_load(self):
        """Force immediate loading of the model (for warmup)"""
        self._ensure_model_loaded()
