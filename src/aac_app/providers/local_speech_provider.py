import warnings

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=".*pkg_resources is deprecated as an API.*",
)

# Core dependency: Whisper itself
try:  # pragma: no cover - simple import gate
    import whisper

    WHISPER_AVAILABLE = True
except ImportError as e:  # pragma: no cover - environment specific
    WHISPER_AVAILABLE = False
    import os

    if os.getenv("AAC_WARN_ON_OPTIONAL_MISSING") == "1":
        warnings.warn(f"Whisper not available: {e}")

# Optional dependencies used only for microphone / VAD features
try:  # pragma: no cover - simple import gate
    import sounddevice as sd

    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

try:  # pragma: no cover - simple import gate
    import soundfile as sf

    SOUNDFILE_AVAILABLE = True
except ImportError:
    sf = None
    SOUNDFILE_AVAILABLE = False

try:  # pragma: no cover - simple import gate
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

try:  # pragma: no cover - simple import gate
    import webrtcvad

    WEBRTC_VAD_AVAILABLE = True
except ImportError:
    webrtcvad = None
    WEBRTC_VAD_AVAILABLE = False

import threading
from queue import Queue
from typing import Callable, Optional

from loguru import logger


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
            
        # Initialize VAD for voice activity detection if available (lightweight)
        if WEBRTC_VAD_AVAILABLE:
            try:
                self.vad = webrtcvad.Vad(2)  # Aggressiveness level 0-3
            except Exception as e:
                logger.warning(f"Failed to initialize VAD: {e}")
                self.vad = None

        if not lazy_load:
            # Immediate loading (backwards compatible for warmup)
            self._load_model()
    
    def _ensure_model_loaded(self):
        """Ensure Whisper model is loaded (lazy loading)"""
        if self._model_loaded:
            return
        self._load_model()
    
    def _load_model(self):
        """Load the Whisper model"""
        if self._model_loaded or not WHISPER_AVAILABLE:
            return
            
        try:
            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}")
            self.model = whisper.load_model(self.model_size, device=self.device)
            self._model_loaded = True
            logger.info(f"Whisper model loaded successfully")
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

        if not (SOUNDDEVICE_AVAILABLE and SOUNDFILE_AVAILABLE):
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
