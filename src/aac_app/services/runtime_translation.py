from __future__ import annotations

import threading
import time
from functools import lru_cache

from loguru import logger

_GoogleTranslator = None
_translation_import_attempted = False
_translation_dependency_warning_emitted = False

# Bound every network translation so a slow or unreachable translation
# service can never stall a request for tens of seconds.
_TRANSLATION_TIMEOUT_SECONDS = 3.0
# After this many consecutive failures the translation service is treated
# as unavailable and attempts are skipped for a cooldown period.
_CIRCUIT_BREAK_CONSECUTIVE_FAILURES = 3
_CIRCUIT_BREAK_COOLDOWN_SECONDS = 60.0

_consecutive_failures = 0
_circuit_open_until = 0.0
_circuit_lock = threading.Lock()


def normalize_language_code(language: str | None) -> str | None:
    """Normalize UI locale tags and provider language values to base codes."""
    if not language:
        return None
    normalized = language.strip().replace("_", "-")
    if not normalized:
        return None
    return normalized.split("-", 1)[0].lower()


def _load_translation_dependency():
    global _GoogleTranslator, _translation_import_attempted
    if _translation_import_attempted:
        return _GoogleTranslator
    _translation_import_attempted = True
    try:
        from deep_translator import GoogleTranslator

        _GoogleTranslator = GoogleTranslator
    except Exception:  # pragma: no cover - keep runtime paths resilient
        _GoogleTranslator = None
    return _GoogleTranslator


@lru_cache(maxsize=16)
def _build_translator(target_lang: str):
    normalized_target = normalize_language_code(target_lang)
    if not normalized_target:
        return None
    translator_class = _load_translation_dependency()
    if translator_class is None:
        return None
    return translator_class(source="auto", target=normalized_target)


def _translate_worker(text: str, target_lang: str) -> str:
    """Run one translation in a worker thread (translator built per-call)."""
    translator = _build_translator(target_lang)
    if translator is None:
        raise RuntimeError("translator unavailable")
    result = translator.translate(text)
    if not result or not str(result).strip():
        raise RuntimeError("empty translation result")
    return str(result).strip()


@lru_cache(maxsize=4096)
def _translate_cached(text: str, target_lang: str) -> str:
    """Translate with a hard timeout. Only successes are cached; failures
    raise so a later request can retry once the service recovers.

    A fresh daemon thread is used per call so a hung translation can never
    block the request (join timeout) or interpreter shutdown (daemon).
    """
    result_holder: dict = {}

    def run() -> None:
        try:
            result_holder["value"] = _translate_worker(text, target_lang)
        except Exception as exc:  # capture for the caller
            result_holder["error"] = exc

    worker = threading.Thread(
        target=run,
        name="aac-translate",
        daemon=True,
    )
    worker.start()
    worker.join(timeout=_TRANSLATION_TIMEOUT_SECONDS)
    if worker.is_alive():
        # The hung daemon thread is abandoned (it dies with the process);
        # treat this call as a failure so the circuit breaker can engage.
        raise TimeoutError(
            f"translation of {text!r} exceeded {_TRANSLATION_TIMEOUT_SECONDS}s"
        )
    if "error" in result_holder:
        raise result_holder["error"]
    return result_holder["value"]


def _translation_disabled() -> bool:
    with _circuit_lock:
        return time.monotonic() < _circuit_open_until


def _note_failure() -> None:
    global _consecutive_failures, _circuit_open_until
    with _circuit_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= _CIRCUIT_BREAK_CONSECUTIVE_FAILURES:
            _consecutive_failures = 0
            _circuit_open_until = (
                time.monotonic() + _CIRCUIT_BREAK_COOLDOWN_SECONDS
            )
            logger.warning(
                "Runtime translation temporarily disabled for {}s after repeated failures",
                _CIRCUIT_BREAK_COOLDOWN_SECONDS,
            )


def _note_success() -> None:
    global _consecutive_failures
    with _circuit_lock:
        _consecutive_failures = 0


def clear_translation_cache() -> None:
    """Reset translation caches and the circuit breaker (mainly for tests)."""
    global _consecutive_failures, _circuit_open_until
    _build_translator.cache_clear()
    _translate_cached.cache_clear()
    with _circuit_lock:
        _consecutive_failures = 0
        _circuit_open_until = 0.0


def translate_text(text: str | None, target_lang: str | None) -> str | None:
    """Best-effort runtime translation that degrades to the original text.

    Results are cached per label/language, each network call is bounded by a
    short timeout, and a circuit breaker skips translation entirely while the
    service is unreachable so suggestions/board loads stay fast.
    """
    global _translation_dependency_warning_emitted
    normalized_target = normalize_language_code(target_lang)
    if not text or not normalized_target:
        return text
    if _load_translation_dependency() is None:
        if not _translation_dependency_warning_emitted:
            logger.warning(
                "deep-translator not installed; returning original text without runtime translation."
            )
            _translation_dependency_warning_emitted = True
        return text
    if _translation_disabled():
        return text

    try:
        translated = _translate_cached(text, normalized_target)
    except Exception as exc:
        _note_failure()
        logger.warning(f"Translation failed for {text!r}: {exc}")
        return text
    _note_success()
    return translated
