"""Optional local neural text-to-speech backed by kokoro-onnx.

Kokoro-82M is a small (~325 MB) StyleTTS2-based model that synthesizes
natural multi-language speech faster than real-time on CPU. It is an
optional dependency: when ``kokoro-onnx`` or the model files are missing,
:class:`LocalTTSProvider` reports itself unavailable and callers fall back
to the browser's SpeechSynthesis API.

Model files (Apache-2.0) are cached under ``data/models/kokoro``:
    - kokoro-v1.0.onnx     (~325 MB)
    - voices-v1.0.bin      (~28 MB)

Spanish voices included in the v1.0 voice pack: ``ef_dora`` (female),
``em_santa`` / ``em_alex`` (male).
"""

from __future__ import annotations

import io
import threading
import wave
from pathlib import Path

from loguru import logger

from ... import config

KOKORO_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
KOKORO_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)
KOKORO_MODEL_FILENAME = "kokoro-v1.0.onnx"
KOKORO_VOICES_FILENAME = "voices-v1.0.bin"

# Language code -> (default female voice, default male voice)
DEFAULT_VOICES: dict[str, tuple[str, str]] = {
    "es": ("ef_dora", "em_santa"),
    "en": ("af_sarah", "am_michael"),
    "fr": ("ff_siwis", "em_alex"),
    "it": ("if_sara", "im_nicola"),
    "pt": ("pf_dora", "pm_alex"),
}

# Kokoro v1.0 voice names known to ship in the bundled voices pack. When the
# pack is present the live catalog is derived from its actual keys instead;
# this list is the deterministic fallback shown before the model is downloaded.
_STATIC_VOICE_NAMES: list[str] = [
    # American English
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore",
    "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    # British English
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    # Spanish
    "ef_dora",
    "em_alex", "em_santa",
    # French
    "ff_siwis", "fm_paulo",
    # Italian
    "if_sara", "im_nicola",
    # Japanese
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    # Portuguese
    "pf_dora", "pm_alex",
    # Chinese (Mandarin)
    "zf_xiaobei", "zm_yunjian", "zm_yunxi", "zm_yunyang",
    # English (espeak pack)
    "cm_arctic", "cm_baldur", "cm_drogba", "cm_dumbledore", "cm_english",
    "cm_ino", "cm_man", "cm_misty", "cm_santa",
]

# First letter of a voice name -> language family (second letter is gender).
_LANG_BY_FAMILY: dict[str, str] = {
    "a": "en",  # American English
    "b": "en",  # British English
    "c": "en",  # espeak English pack
    "e": "es",
    "f": "fr",
    "i": "it",
    "j": "ja",
    "p": "pt",
    "z": "zh",
}
_REGION_BY_FAMILY: dict[str, str] = {
    "a": "american",
    "b": "british",
}


def _voice_info_from_name(name: str) -> dict | None:
    """Derive language/gender/region from a Kokoro voice name."""
    if len(name) < 4 or name[1] not in ("f", "m"):
        return None
    family = name[0]
    language = _LANG_BY_FAMILY.get(family)
    if language is None:
        return None
    return {
        "name": name,
        "language": language,
        "gender": "female" if name[1] == "f" else "male",
        "region": _REGION_BY_FAMILY.get(family),
    }


def _pack_voice_names() -> list[str] | None:
    """Return the voice keys stored in the downloaded pack, or None."""
    try:
        if not model_files_present():
            return None
        import numpy as np

        with np.load(kokoro_voices_path(), allow_pickle=True) as data:
            return sorted(data.files)
    except Exception:  # pragma: no cover - environment dependent
        return None


# Catalog is static for the process lifetime (the pack never changes at
# runtime); cleared by reset_local_tts_provider() for tests and installs.
_voice_catalog_cache: list[dict] | None = None


def list_kokoro_voices() -> list[dict]:
    """Return the available Kokoro voices: name, language, gender, region.

    When the model pack is present the exact voice keys are read from it;
    otherwise the bundled static catalog is returned so the Settings picker
    can be populated before the model is downloaded.
    """
    global _voice_catalog_cache
    if _voice_catalog_cache is not None:
        return _voice_catalog_cache
    with _import_lock:
        if _voice_catalog_cache is not None:
            return _voice_catalog_cache
        names = _pack_voice_names()
        if names is None:
            names = _STATIC_VOICE_NAMES
        catalog = []
        for name in names:
            info = _voice_info_from_name(name)
            if info is not None:
                catalog.append(info)
        catalog.sort(key=lambda v: (v["language"], v["region"] or "", v["name"]))
        _voice_catalog_cache = catalog
    return _voice_catalog_cache


def _known_voice_names() -> set[str]:
    return {v["name"] for v in list_kokoro_voices()}

# Map any common locale tag to the exact code the bundled espeak backend
# accepts (they are inconsistent: en-us vs es vs fr-fr vs it/pt/de...).
_ESPEAK_LANG_CODES: dict[str, str] = {
    "en": "en-us",
    "en-us": "en-us",
    "en-gb": "en-us",
    "es": "es",
    "es-es": "es",
    "es-mx": "es",
    "fr": "fr-fr",
    "fr-fr": "fr-fr",
    "it": "it",
    "it-it": "it",
    "pt": "pt",
    "pt-pt": "pt",
    "pt-br": "pt",
    "de": "de",
    "de-de": "de",
    "ja": "ja",
    "zh": "zh",
    "zh-cn": "zh",
    "ko": "ko",
}


def _espeak_lang_code(lang: str | None) -> str:
    """Normalize a locale tag to the code the Kokoro espeak backend accepts."""
    normalized = (lang or "es").strip().replace("_", "-").lower()
    return _ESPEAK_LANG_CODES.get(normalized, "es")

_available = False
_import_error: str | None = None
_import_attempted = False
_import_lock = threading.Lock()


def _module_available() -> bool:
    """Return whether kokoro_onnx can be imported (attempted only once)."""
    global _available, _import_error, _import_attempted
    if _import_attempted:
        return _available
    with _import_lock:
        if _import_attempted:
            return _available
        _import_attempted = True
        try:
            from kokoro_onnx import Kokoro  # noqa: F401

            _available = True
        except Exception as exc:  # pragma: no cover - environment dependent
            _import_error = str(exc)
            _available = False
    return _available


def kokoro_import_error() -> str | None:
    """Return why kokoro-onnx is unavailable, if it is."""
    _module_available()
    return _import_error


def kokoro_model_dir() -> Path:
    """Return the directory where Kokoro model files are cached."""
    return config.get_data_path("models/kokoro")


def kokoro_model_path() -> Path:
    """Return the expected path of the ONNX model file."""
    return kokoro_model_dir() / KOKORO_MODEL_FILENAME


def kokoro_voices_path() -> Path:
    """Return the expected path of the voices file."""
    return kokoro_model_dir() / KOKORO_VOICES_FILENAME


def model_files_present() -> bool:
    """Return whether both model files exist and look valid (non-empty)."""
    model = kokoro_model_path()
    voices = kokoro_voices_path()
    return (
        model.is_file()
        and model.stat().st_size > 1_000_000
        and voices.is_file()
        and voices.stat().st_size > 1_000_000
    )


def download_kokoro_model() -> bool:
    """Download both Kokoro model files into the data/models cache."""
    import urllib.request

    directory = kokoro_model_dir()
    directory.mkdir(parents=True, exist_ok=True)

    targets = (
        (KOKORO_MODEL_URL, directory / KOKORO_MODEL_FILENAME),
        (KOKORO_VOICES_URL, directory / KOKORO_VOICES_FILENAME),
    )
    for url, dest in targets:
        if dest.is_file() and dest.stat().st_size > 1_000_000:
            logger.info("Kokoro model file already present: {}", dest.name)
            continue
        logger.info("Downloading Kokoro model file {} -> {}", url.split("/")[-1], dest)
        try:
            with urllib.request.urlopen(url, timeout=600) as response, open(
                dest, "wb"
            ) as out:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    out.write(chunk)
        except Exception as exc:
            logger.error("Failed to download {}: {}", url, exc)
            return False

    if model_files_present():
        logger.success("Kokoro model files are ready in {}", directory)
        return True
    logger.error("Kokoro model download did not produce valid model files")
    return False


class LocalTTSProvider:
    """Lazy, process-wide local neural TTS synthesizer."""

    def __init__(self, lazy_load: bool = True):
        self._kokoro = None
        self._load_lock = threading.Lock()
        self._load_attempted = not lazy_load
        if not lazy_load:
            self._ensure_loaded()

    def is_available(self) -> bool:
        """Return whether local TTS can synthesize right now."""
        return _module_available() and model_files_present()

    def is_installed(self) -> bool:
        """Return whether the kokoro-onnx package is installed (model may be absent)."""
        return _module_available()

    def _ensure_loaded(self):
        if self._kokoro is not None:
            return self._kokoro
        with self._load_lock:
            if self._kokoro is not None:
                return self._kokoro
            if not self.is_available():
                return None
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(
                str(kokoro_model_path()), str(kokoro_voices_path())
            )
            logger.info("LocalTTSProvider loaded Kokoro model")
        return self._kokoro

    def synthesize(
        self,
        text: str,
        lang: str = "es",
        voice: str | None = None,
        speed: float = 1.0,
    ) -> bytes | None:
        """
        Synthesize ``text`` into a 16-bit mono WAV and return its bytes.

        Returns ``None`` when the provider is unavailable so callers can
        fall back to another TTS engine without error handling.
        """
        if not text or not text.strip():
            return None
        kokoro = self._ensure_loaded()
        if kokoro is None:
            return None

        base_lang = (lang or "es").split("-")[0].lower()
        espeak_lang = _espeak_lang_code(lang)
        resolved_voice = voice or "default"
        if resolved_voice in ("default", "female", "male"):
            female, male = DEFAULT_VOICES.get(base_lang, DEFAULT_VOICES["es"])
            resolved_voice = female if resolved_voice in ("default", "female") else male
        else:
            voice_info = _voice_info_from_name(resolved_voice)
            if voice_info is None or resolved_voice not in _known_voice_names():
                # Unknown voice (e.g. a browser voiceURI leaking through the
                # settings): fall back to the language default instead of failing.
                female, _male = DEFAULT_VOICES.get(base_lang, DEFAULT_VOICES["es"])
                resolved_voice = female
            else:
                # A specific voice drives the spoken language so the Settings
                # picker works regardless of the current UI language.
                espeak_lang = _espeak_lang_code(voice_info["language"])

        try:
            samples, sample_rate = kokoro.create(
                text,
                voice=resolved_voice,
                speed=speed,
                lang=espeak_lang,
            )
            return _samples_to_wav(samples, sample_rate)
        except Exception as exc:
            logger.warning("Kokoro synthesis failed: {}", exc)
            return None


def _samples_to_wav(samples, sample_rate: int) -> bytes:
    """Encode float samples as a 16-bit mono WAV byte string.

    numpy is imported lazily so importing the provider module (and thus the
    API) never pulls the heavy optional dependency tree at startup.
    """
    import numpy as np

    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


# Process-wide singleton (lazy; the model is only loaded on first synthesis).
_local_tts_provider: LocalTTSProvider | None = None
_provider_lock = threading.Lock()


def get_local_tts_provider() -> LocalTTSProvider:
    """Return the shared LocalTTSProvider instance."""
    global _local_tts_provider
    if _local_tts_provider is None:
        with _provider_lock:
            if _local_tts_provider is None:
                _local_tts_provider = LocalTTSProvider(lazy_load=True)
    return _local_tts_provider


def reset_local_tts_provider() -> None:
    """Drop the singleton and clear cached import state.

    Used by tests and after a runtime ``uv sync --extra tts`` install so the
    engine can be picked up without a full server restart (the failed-import
    cache from startup would otherwise keep the provider unavailable).
    """
    global _local_tts_provider, _available, _import_error, _import_attempted
    global _voice_catalog_cache
    with _provider_lock:
        _local_tts_provider = None
    with _import_lock:
        _available = False
        _import_error = None
        _import_attempted = False
    _voice_catalog_cache = None
