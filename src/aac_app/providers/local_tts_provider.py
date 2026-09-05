"""Optional local neural text-to-speech backed by kokoro-onnx.

Kokoro-82M is a small (~325 MB) StyleTTS2-based model that synthesizes
natural multi-language speech faster than real-time on CPU. The source
launcher installs ``kokoro-onnx`` and prepares the model files before the
server starts. If either is unavailable, :class:`LocalTTSProvider` reports
itself unavailable and the selected Kokoro provider refuses to speak.

Model files (Apache-2.0) are cached under ``data/models/kokoro``:
    - kokoro-v1.0.onnx     (~325 MB)
    - voices-v1.0.bin      (~28 MB)

Spanish voices included in the v1.0 voice pack: ``ef_dora`` (female),
``em_santa`` / ``em_alex`` (male).
"""

from __future__ import annotations

import io
import os
import tempfile
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

# Pause phonemes prepended at speed > 1 so the model's initial-generation
# corruption lands on silence instead of the first word. Only used on the
# legacy fallback path; the primary speed path is atempo (see synthesize()).
_ONSET_GUARD_PHONEMES = ":" * 5

_av_available: bool | None = None


def _atempo_available() -> bool:
    """PyAV (a faster-whisper dependency) provides ffmpeg's atempo filter."""
    global _av_available
    if _av_available is None:
        try:
            import av  # noqa: F401

            _av_available = True
        except ImportError:
            _av_available = False
    return _av_available


def _apply_atempo(samples, sample_rate: int, speed: float):
    """Time-stretch float mono samples without shifting pitch.

    Kokoro's own speed parameter also scales the BOS/EOS boundary tokens,
    and the vocoder voices that resized boundary window as a phantom leading
    vowel ("e"/"a") — blatant on isolated words (hexgrad/kokoro#344). The
    documented workaround is to synthesize at speed 1.0 and stretch the
    result afterwards; ffmpeg's atempo preserves formants and never touches
    the onset.
    """
    import av
    import numpy as np

    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    frame = av.AudioFrame.from_ndarray(pcm16.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = int(sample_rate)
    graph = av.filter.Graph()
    source = graph.add(
        "abuffer",
        args=(
            f"time_base=1/{int(sample_rate)}:sample_rate={int(sample_rate)}"
            ":sample_fmt=s16:channel_layout=mono"
        ),
    )
    tempo = graph.add("atempo", f"{speed:.4f}")
    sink = graph.add("abuffersink")
    source.link_to(tempo)
    tempo.link_to(sink)
    graph.configure()
    graph.push(frame)
    graph.push(None)  # flush so the tail is not left in the filter
    chunks = []
    while True:
        try:
            out = sink.pull()
        except (BlockingIOError, EOFError, av.error.FFmpegError):
            break
        chunks.append(np.frombuffer(out.to_ndarray().tobytes(), dtype=np.int16))
    if not chunks:
        return samples
    return np.concatenate(chunks).astype(np.float32) / 32768

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
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("Failed to load Kokoro voice catalog: {}", exc)
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


def _safe_import_reason(exc: Exception) -> str:
    """A client-safe reason for a missing Kokoro engine.

    ``kokoro_import_error()`` is exposed to authenticated clients in the
    voice-status payload, so the raw exception text (which can embed paths
    or environment details) is never stored; the full detail stays in the
    debug log instead.
    """
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        return f"Missing Python module: {exc.name}"
    return type(exc).__name__


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
            _import_error = _safe_import_reason(exc)
            _available = False
            logger.debug("Kokoro import unavailable: {}", exc)
    return _available


def kokoro_import_error() -> str | None:
    """Return why kokoro-onnx is unavailable, if it is."""
    _module_available()
    return _import_error


def kokoro_model_dir() -> Path:
    """Return the writable directory where Kokoro model files are downloaded."""
    return config.get_data_path("models/kokoro")


def _kokoro_model_dir_read() -> Path:
    """Return the best model directory: bundled first, then writable fallback.

    Packaged releases ship the model under the read-only ``models/kokoro``
    bundle directory so the application works fully offline.
    """
    bundled = config.get_bundled_models_dir()
    if bundled is not None and (bundled / "kokoro" / KOKORO_MODEL_FILENAME).is_file():
        return bundled / "kokoro"
    return kokoro_model_dir()


def kokoro_model_path() -> Path:
    """Return the expected path of the ONNX model file."""
    return _kokoro_model_dir_read() / KOKORO_MODEL_FILENAME


def kokoro_voices_path() -> Path:
    """Return the expected path of the voices file."""
    return _kokoro_model_dir_read() / KOKORO_VOICES_FILENAME


def model_files_present() -> bool:
    """Return whether both model files exist and look valid (non-empty)."""
    try:
        model = kokoro_model_path()
        voices = kokoro_voices_path()
        return (
            model.is_file()
            and model.stat().st_size > 1_000_000
            and voices.is_file()
            and voices.stat().st_size > 1_000_000
        )
    except OSError as exc:
        # Optional model caches may be on removable or restricted storage;
        # report them as unavailable instead of turning status/TTS into a 500.
        logger.debug("Kokoro model cache cannot be inspected: {}", exc)
        return False


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
        temporary_path: Path | None = None
        try:
            # Keep an existing valid file usable if a network response fails
            # halfway through. The temporary file lives beside the target so
            # os.replace is atomic on the same filesystem.
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=directory,
                prefix=f".{dest.name}.",
                suffix=".tmp",
                delete=False,
            ) as out:
                temporary_path = Path(out.name)
                with urllib.request.urlopen(url, timeout=600) as response:
                    while True:
                        chunk = response.read(1024 * 512)
                        if not chunk:
                            break
                        out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary_path, dest)
            temporary_path = None
        except Exception as exc:
            logger.error("Failed to download {}: {}", url, exc)
            return False
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

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

    def is_ready(self) -> bool:
        """Return whether the Kokoro model is loaded in memory (post-warmup)."""
        return self._kokoro is not None

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

    def warmup(self) -> bool:
        """Load the Kokoro model now so the first synthesis is fast.

        The model is normally loaded lazily on the first ``synthesize`` call;
        warming it moves that one-time cost off the critical path so a page's
        first utterance does not wait for the ~325 MB ONNX model to be read.
        Safe to call repeatedly: the load is guarded by a lock and runs once.
        """
        return self._ensure_loaded() is not None

    def synthesize(
        self,
        text: str,
        lang: str = "es",
        voice: str | None = None,
        speed: float = 1.0,
    ) -> bytes | None:
        """
        Synthesize ``text`` into a 16-bit mono WAV and return its bytes.

        Returns ``None`` when the provider is unavailable so callers can report
        the selected provider failure without producing speech through another
        engine.
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
                raise ValueError(f"Unknown Kokoro voice: {resolved_voice}")
            else:
                # A specific voice drives the spoken language so the Settings
                # picker works regardless of the current UI language.
                espeak_lang = _espeak_lang_code(voice_info["language"])

        try:
            # Kokoro quirks worked around here:
            # 1. The model's speed parameter corrupts the clip boundaries
            #    (hexgrad/kokoro#344): the duration scaling also resizes the
            #    BOS/EOS tokens and the vocoder voices that window as a
            #    phantom leading vowel ("e"/"a"), blatant on isolated words.
            #    The documented workaround is to synthesize at speed 1.0 and
            #    stretch afterwards with the pitch-preserving atempo filter.
            #    Only without PyAV do we pass speed != 1 to the model, where
            #    a short run of pause tokens (":" is Kokoro's pause phoneme)
            #    absorbs most of the onset corruption.
            # 2. kokoro-onnx's default trimmer uses a peak-relative threshold
            #    that can cut soft word onsets, so trimming is disabled; the
            #    untrimmed edge padding is only ~150-200 ms of silence.
            phonemes = kokoro.tokenizer.phonemize(text, espeak_lang)
            stretch = speed != 1.0 and _atempo_available()
            model_speed = 1.0 if stretch else speed
            if model_speed > 1.0:
                phonemes = _ONSET_GUARD_PHONEMES + phonemes
            samples, sample_rate = kokoro.create(
                phonemes,
                voice=resolved_voice,
                speed=model_speed,
                lang=espeak_lang,
                is_phonemes=True,
                trim=False,
            )
            if stretch:
                try:
                    samples = _apply_atempo(samples, sample_rate, speed)
                except Exception as exc:
                    # Clean audio at normal tempo beats no audio.
                    logger.warning("atempo stretch failed, keeping 1.0x audio: {}", exc)
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


def reset_local_tts_provider(*, clear_import_state: bool = False) -> None:
    """Drop the singleton and optionally clear cached import state.

    Resetting the provider instance is safe after settings/model changes. The
    import capability cache is cleared only after runtime installation; this
    keeps test doubles and an already-detected optional dependency stable.
    """
    global _local_tts_provider, _available, _import_error, _import_attempted
    global _voice_catalog_cache
    with _provider_lock:
        _local_tts_provider = None
    if clear_import_state:
        with _import_lock:
            _available = False
            _import_error = None
            _import_attempted = False
    _voice_catalog_cache = None
