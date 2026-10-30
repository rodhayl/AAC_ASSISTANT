try:
    import pyttsx3

    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    import warnings

    warnings.warn("pyttsx3 not available, TTS functionality disabled")

import threading
from typing import Callable, Dict, List, Optional

from loguru import logger


class LocalTTSProvider:
    """100% local TTS using system voices"""

    def __init__(self):
        logger.info("Initializing local TTS provider")

        if not PYTTSX3_AVAILABLE:
            logger.error("pyttsx3 not available. TTS functionality disabled.")
            self.engine = None
            self.voices = []
            return

        try:
            self.engine = pyttsx3.init()
            self._configure_defaults()
            logger.info("TTS provider initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize TTS: {e}")
            self.engine = None
            self.voices = []

    def _configure_defaults(self):
        """Set reasonable defaults"""
        self.engine.setProperty("rate", 150)  # Words per minute
        self.engine.setProperty("volume", 0.9)  # 0.0 to 1.0

        # Try to set a default voice if available
        voices = self.engine.getProperty("voices")
        if voices:
            # Prefer English voices if available
            for voice in voices:
                if hasattr(voice, "languages") and voice.languages:
                    if "en" in str(voice.languages[0]).lower():
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

        if not PYTTSX3_AVAILABLE or self.engine is None:
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

    def speak_async(self, text: str, callback: Optional[Callable[[], None]] = None):
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

    def get_available_voices(self) -> List[Dict]:
        """List all system voices"""
        voices = []
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
        try:
            self.engine.setProperty("voice", voice_id)
            logger.info(f"Voice changed to: {voice_id}")
        except Exception as e:
            logger.error(f"Failed to set voice {voice_id}: {e}")

    def set_rate(self, rate: int):
        """Set speech rate (100-200 typical)"""
        try:
            self.engine.setProperty("rate", rate)
            logger.info(f"Speech rate set to: {rate}")
        except Exception as e:
            logger.error(f"Failed to set rate {rate}: {e}")

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)"""
        try:
            self.engine.setProperty("volume", volume)
            logger.info(f"Volume set to: {volume}")
        except Exception as e:
            logger.error(f"Failed to set volume {volume}: {e}")

    def stop(self):
        """Stop current speech"""
        try:
            self.engine.stop()
            logger.info("Speech stopped")
        except Exception as e:
            logger.error(f"Failed to stop speech: {e}")

    def test_voice(self, text: str = "Hello! This is a voice test."):
        """Test current voice settings"""
        logger.info(f"Testing voice with: {text}")
        self.speak(text)

    def get_voice_info(self, voice_id: str) -> Optional[Dict]:
        """Get detailed information about a specific voice"""
        voices = self.get_available_voices()
        for voice in voices:
            if voice["id"] == voice_id:
                return voice
        return None
