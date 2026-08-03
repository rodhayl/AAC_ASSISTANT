import importlib.util
import threading
from collections.abc import Callable

from loguru import logger


def _module_available(module_name: str) -> bool:
    """Check for an optional module without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


PYTTSX3_AVAILABLE = _module_available("pyttsx3")
pyttsx3 = None


class LocalTTSProvider:
    """100% local TTS using system voices"""

    def __init__(self):
        logger.info("Initializing local TTS provider (lazy mode)")
        self.engine = None
        self.voices = []
        self._engine_init_attempted = False

    def _ensure_engine(self) -> bool:
        """Import and initialize pyttsx3 on the first speech operation."""
        global PYTTSX3_AVAILABLE, pyttsx3
        if self.engine is not None:
            return True
        if self._engine_init_attempted:
            return False
        self._engine_init_attempted = True
        if not PYTTSX3_AVAILABLE:
            logger.error("pyttsx3 not available. TTS functionality disabled.")
            return False
        try:
            import pyttsx3 as pyttsx3_module

            pyttsx3 = pyttsx3_module
            self.engine = pyttsx3.init()
            self._configure_defaults()
            logger.info("TTS provider initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize TTS: {e}")
            self.engine = None
            self.voices = []
            return False

    def _configure_defaults(self):
        """Set reasonable defaults"""
        self.engine.setProperty("rate", 150)  # Words per minute
        self.engine.setProperty("volume", 0.9)  # 0.0 to 1.0

        # Try to set a default voice if available
        voices = self.engine.getProperty("voices")
        if voices:
            # Prefer English voices if available
            for voice in voices:
                if (
                    hasattr(voice, "languages")
                    and voice.languages
                    and "en" in str(voice.languages[0]).lower()
                ):
                    self.engine.setProperty("voice", voice.id)
                    logger.info(f"Set default voice: {voice.name}")
                    break
            else:
                # Use first available voice
                self.engine.setProperty("voice", voices[0].id)
                logger.info(f"Set default voice: {voices[0].name}")

    def speak(self, text: str, blocking: bool = False):
        """Speak text"""
        if not text or not text.strip():
            logger.warning("Empty text provided to speak")
            return

        if not self._ensure_engine():
            logger.error("TTS not available - dependencies missing")
            return

        try:
            logger.debug(f"Speaking text: {text[:50]}...")
            self.engine.say(text)
            if blocking:
                self.engine.runAndWait()
            else:
                # Run in background thread for non-blocking
                threading.Thread(target=self.engine.runAndWait, daemon=True).start()
        except Exception as e:
            logger.error(f"Speech failed: {e}")

    def synthesize(self, text: str, blocking: bool = False):
        """Compatibility alias for callers that use the synthesis name."""
        self.speak(text, blocking=blocking)

    def speak_async(self, text: str, callback: Callable[[], None] | None = None):
        """Non-blocking speech"""

        def _speak():
            try:
                self.speak(text, blocking=True)
                if callback:
                    callback()
            except Exception as e:
                logger.error(f"Async speech failed: {e}")
                if callback:
                    callback()

        threading.Thread(target=_speak, daemon=True).start()

    def get_available_voices(self) -> list[dict]:
        """List all system voices"""
        voices = []
        if not self._ensure_engine():
            return voices
        try:
            for voice in self.engine.getProperty("voices"):
                voice_info = {
                    "id": voice.id,
                    "name": voice.name,
                    "languages": voice.languages if hasattr(voice, "languages") else [],
                    "gender": voice.gender if hasattr(voice, "gender") else None,
                }
                voices.append(voice_info)
                logger.debug(f"Found voice: {voice_info['name']}")
        except Exception as e:
            logger.error(f"Failed to get voices: {e}")

        return voices

    def set_voice(self, voice_id: str):
        """Change active voice"""
        if not self._ensure_engine():
            return
        try:
            self.engine.setProperty("voice", voice_id)
            logger.info(f"Voice changed to: {voice_id}")
        except Exception as e:
            logger.error(f"Failed to set voice {voice_id}: {e}")

    def set_rate(self, rate: int):
        """Set speech rate (100-200 typical)"""
        if not self._ensure_engine():
            return
        try:
            self.engine.setProperty("rate", rate)
            logger.info(f"Speech rate set to: {rate}")
        except Exception as e:
            logger.error(f"Failed to set rate {rate}: {e}")

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)"""
        if not self._ensure_engine():
            return
        try:
            self.engine.setProperty("volume", volume)
            logger.info(f"Volume set to: {volume}")
        except Exception as e:
            logger.error(f"Failed to set volume {volume}: {e}")

    def stop(self):
        """Stop current speech"""
        if not self._ensure_engine():
            return
        try:
            self.engine.stop()
            logger.info("Speech stopped")
        except Exception as e:
            logger.error(f"Failed to stop speech: {e}")

    def test_voice(self, text: str = "Hello! This is a voice test."):
        """Test current voice settings"""
        logger.info(f"Testing voice with: {text}")
        self.speak(text)

    def get_voice_info(self, voice_id: str) -> dict | None:
        """Get detailed information about a specific voice"""
        voices = self.get_available_voices()
        for voice in voices:
            if voice["id"] == voice_id:
                return voice
        return None
