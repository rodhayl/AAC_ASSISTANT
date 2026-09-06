"""
Rebuild N-gram prediction models from real symbol usage logs.

The bundled models under ``src/aac_app/data/ngrams`` are a hand-written
cold-start vocabulary. This module turns actual ``SymbolUsageLog`` rows into
the same ``{"bigrams": {prefix: {next: probability}}}`` format, fusing the
observed transitions over the bundled seed so the model keeps core-coverage
while reflecting what users really say. Rebuilt models are written to the
writable ``data/ngrams`` directory; the prediction service prefers them over
the bundled files, so the effective model is learned from real usage.
"""

import asyncio
import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Symbol, SymbolUsageLog
from .runtime_translation import LIKE_ESCAPE, escape_like_literal, normalize_language_code

# A new utterance begins when the session changes or when more than this many
# seconds separate consecutive logs; mirrors SymbolAnalytics sequence logic.
UTTERANCE_GAP_SECONDS = 300

# Locales the rebuilt model covers by default (same set the ARASAAC import uses).
DEFAULT_LOCALES: tuple[str, ...] = ("es", "en")


def _bundled_bigrams(locale: str) -> dict[str, dict[str, float]]:
    """Load the hand-written bundled bigrams as the cold-start seed."""
    from src import config

    path = config.get_ngrams_path() / f"{locale}.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle).get("bigrams", {})
    except Exception as exc:
        logger.warning("Failed to read bundled n-gram model {}: {}", path, exc)
        return {}


def _resolve_log_language(session: Session, log: SymbolUsageLog) -> str | None:
    """Return the model locale for one usage log.

    Uses the linked symbol's language when available, then falls back to
    matching the stored label against the symbol catalog in either locale.
    Logs that cannot be attributed to a supported locale are ignored.
    """
    if log.symbol_id is not None:
        language = (
            session.query(Symbol.language).filter(Symbol.id == log.symbol_id).scalar()
        )
        if language:
            return normalize_language_code(language) or None

    label = (log.symbol_label or "").strip().casefold()
    if not label:
        return None
    # The stored label is user content from usage logs: a ``%`` or ``_`` in
    # it must match literally, never act as a LIKE wildcard that attributes
    # the log to the wrong locale (e.g. a "wash_hands" log matching a
    # "washXhands" symbol).
    literal = escape_like_literal(label)
    for locale in DEFAULT_LOCALES:
        exists = (
            session.query(Symbol.id)
            .filter(
                Symbol.language == locale,
                Symbol.label.ilike(literal, escape=LIKE_ESCAPE),
            )
            .first()
        )
        if exists:
            return locale
    return None


def collect_usage_bigrams(
    db: Session | None = None,
) -> dict[str, dict[tuple[str, str], int]]:
    """Count observed ``(prefix, next)`` bigrams per locale from real usage.

    Utterances are segmented with the same session/5-minute-gap rules the
    analytics service uses, so consecutive selections inside one utterance
    become bigrams while unrelated selections never pair up.
    """
    bigrams: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: Counter())

    def scan(session: Session) -> None:
        logs = (
            session.query(SymbolUsageLog)
            .order_by(
                SymbolUsageLog.user_id,
                SymbolUsageLog.session_id,
                SymbolUsageLog.timestamp,
                SymbolUsageLog.position_in_utterance,
                SymbolUsageLog.id,
            )
            .yield_per(1000)
        )

        current_user_id: int | None = None
        current_locale: str | None = None
        current_sequence: list[str] = []
        current_session = None
        current_timestamp = None
        last_position: int | None = None

        def flush_sequence() -> None:
            nonlocal current_locale
            if current_locale is None or len(current_sequence) < 2:
                return
            counter = bigrams[current_locale]
            for first, second in zip(
                current_sequence, current_sequence[1:], strict=False
            ):
                if first and second:
                    counter[(first, second)] += 1

        def new_utterance(log) -> bool:
            """Return True when ``log`` starts a fresh utterance.

            Besides a session change or a long gap, a position that does not
            advance (a reset to 0, or any decrease) marks a new utterance:
            consecutive selections inside one utterance carry increasing
            positions, so single-symbol utterances (position 0) never chain
            into a fake sequence.
            """
            user_changed = current_user_id != log.user_id
            session_changed = current_session != log.session_id
            time_gap = (
                current_timestamp is not None
                and log.timestamp is not None
                and (log.timestamp - current_timestamp)
                > timedelta(seconds=UTTERANCE_GAP_SECONDS)
            )
            position_reset = (
                last_position is not None
                and log.position_in_utterance is not None
                and log.position_in_utterance <= last_position
            )
            return user_changed or session_changed or bool(time_gap) or position_reset

        for log in logs:
            if new_utterance(log):
                flush_sequence()
                current_sequence = []
                current_locale = None

            locale = _resolve_log_language(session, log)
            if locale is None:
                current_sequence = []
                current_locale = None
                current_user_id = log.user_id
                current_session = log.session_id
                current_timestamp = log.timestamp
                last_position = log.position_in_utterance
                continue

            # A reused learning session can contain symbols from more than one
            # locale. Never assign a mixed-language sequence to whichever
            # locale happened to be logged last.
            if current_locale is not None and current_locale != locale:
                flush_sequence()
                current_sequence = []

            current_sequence.append((log.symbol_label or "").strip())
            current_user_id = log.user_id
            current_locale = locale
            current_session = log.session_id
            current_timestamp = log.timestamp
            last_position = log.position_in_utterance

        flush_sequence()

    if db is not None:
        scan(db)
    else:
        with get_session() as session:
            scan(session)

    return {locale: dict(counter) for locale, counter in bigrams.items()}


def _to_probabilities(
    counts: dict[tuple[str, str], int],
) -> dict[str, dict[str, float]]:
    """Convert raw bigram counts into per-prefix probability distributions."""
    prefix_totals: dict[str, int] = defaultdict(int)
    for (first, _second), count in counts.items():
        prefix_totals[first] += count

    model: dict[str, dict[str, float]] = defaultdict(dict)
    for (first, second), count in counts.items():
        model[first][second] = round(count / prefix_totals[first], 4)
    return dict(model)


def _merge_models(
    bundled: dict[str, dict[str, float]],
    learned: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Fuse learned transitions over the bundled seed.

    Observed prefixes replace/augment the bundled distribution; unobserved
    bundled entries are kept so core vocabulary coverage survives while the
    real usage data is sparse. Learned probabilities win where they exist.
    """
    merged: dict[str, dict[str, float]] = {}
    for prefix, next_words in bundled.items():
        merged[prefix] = {**next_words}
    for prefix, next_words in learned.items():
        if prefix in merged:
            merged[prefix].update(next_words)
        else:
            merged[prefix] = dict(next_words)
    return merged


def rebuild_ngram_models(
    db: Session | None = None,
    locales: tuple[str, ...] = DEFAULT_LOCALES,
) -> dict[str, Path]:
    """Rebuild the writable n-gram models from real usage logs.

    Returns a mapping of locale -> written model path. The bundled JSON files
    are never modified; rebuilt models land in ``data/ngrams`` and take
    precedence at prediction time.
    """
    from src import config

    from ..services.prediction_service import prediction_service

    learned = collect_usage_bigrams(db=db)
    written: dict[str, Path] = {}
    output_dir = config.get_data_path("ngrams")
    output_dir.mkdir(parents=True, exist_ok=True)

    for locale in locales:
        locale_key = normalize_language_code(locale) or locale
        learned_model = _to_probabilities(learned.get(locale_key, {}))
        merged = _merge_models(_bundled_bigrams(locale_key), learned_model)

        output_path = output_dir / f"{locale_key}.json"
        temporary_path: Path | None = None
        try:
            # Readers may load models while the periodic rebuild runs. Write
            # beside the destination and atomically replace it only after the
            # complete JSON document has been flushed.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=output_dir,
                prefix=f".{locale_key}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump({"bigrams": merged}, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, output_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        written[locale_key] = output_path

        learned_count = sum(len(words) for words in learned_model.values())
        logger.info(
            "Rebuilt n-gram model for locale={} (learned bigrams: {}) -> {}",
            locale_key,
            learned_count,
            output_path,
        )

        # The singleton caches models once loaded; drop the stale entry so the
        # next prediction request observes the freshly rebuilt file.
        prediction_service._models.pop(locale_key, None)

    return written


async def run_periodic_ngram_rebuild(
    locales: tuple[str, ...] = DEFAULT_LOCALES,
    interval_seconds: int = 3600,
    *,
    rebuild_fn=rebuild_ngram_models,
) -> None:
    """Rebuild n-gram models now and then every ``interval_seconds``.

    Runs one rebuild immediately (preserving the startup behaviour) and keeps
    refreshing while the server runs, so the model learns from new usage
    without a restart. A non-positive interval performs the single startup
    rebuild and returns. Each iteration runs in a thread and is isolated:
    a transient failure is logged without killing the loop. The coroutine
    exits promptly on cancellation (used during shutdown).
    """
    while True:
        try:
            await asyncio.to_thread(rebuild_fn, None, locales)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.error(f"Periodic n-gram rebuild failed: {exc}")
        if interval_seconds <= 0:
            return
        await asyncio.sleep(interval_seconds)
