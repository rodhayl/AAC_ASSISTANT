"""
Background auto-generation of SVG pictograms for catalog-missing words.

When the Smartbar suggests a text-only word (no catalog symbol exists), this
service generates the pictogram off the request path, persists it as a real
``Symbol`` row with an SVG file, and indexes it — so the word never needs to
be generated again: the next prediction resolves it against the catalog and
returns a real image.

Latency contract for the Smartbar:
    * ``ensure_symbol_generated`` only does cheap in-memory dedup checks and
      spawns a daemon thread; it never calls the LLM synchronously.
    * The background thread re-checks the catalog right before generating, so
      a symbol that appeared meanwhile is never regenerated.
    * Failed attempts are recorded with a cooldown, so a broken provider is
      not hammered once per keystroke; the word keeps working as text-only
      until a later attempt succeeds.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC

from loguru import logger

from src import config

# Loaded lazily to keep provider construction off the import path.
_llm_provider_factory: Callable[[], object] | None = None


def set_llm_provider_factory(factory: Callable[[], object] | None) -> None:
    """Inject the provider factory used by background generation.

    The production wiring (``src/api/deps/providers``) supplies this at
    startup; tests can point it at a fake. Without a factory the service is a
    no-op, so the Smartbar degrades gracefully to text-only words.
    """
    global _llm_provider_factory
    _llm_provider_factory = factory


@dataclass(frozen=True)
class _PendingKey:
    """Dedup key: (normalized label, language)."""

    label: str
    language: str


# In-flight generation per (label, language) so concurrent Smartbar requests
# for the same word do not fire duplicate LLM calls. Failed keys keep their
# timestamp so the provider is not retried until the cooldown elapses.
_lock = threading.RLock()
_in_flight: set[_PendingKey] = set()
_recent_failures: dict[_PendingKey, float] = {}

# Serializes the budget check + LLM call + persist in background threads so
# the daily cap is a hard limit even under concurrent Smartbar requests.
_generation_lock = threading.Lock()

_RETRY_COOLDOWN_SECONDS = 5 * 60


def _normalize_label(label: str) -> str:
    return (label or "").strip().lower()


def _generate_sync_callable():
    """Return the provider's synchronous generator, or None when unavailable."""
    if _llm_provider_factory is None:
        return None
    try:
        provider = _llm_provider_factory()
        generate_sync = getattr(provider, "generate_sync", None)
        return generate_sync if callable(generate_sync) else None
    except Exception as exc:
        logger.warning("LLM provider unavailable for symbol autogen: {}", exc)
        return None


def _has_catalog_symbol(label: str) -> bool:
    """True when a symbol with this label already exists (any language).

    The prediction catalog is keyed by normalized label across all locales,
    and the text-only suggestion only fires when that lookup misses — so the
    background re-check must use the same label-only semantics, not narrower
    (label, language) matching that would regenerate an existing symbol.
    """
    from src.aac_app.db import get_session
    from src.aac_app.models import Symbol

    normalized = _normalize_label(label)
    if not normalized:
        return True  # Nothing to generate for empty labels.
    with get_session() as session:
        return (
            session.query(Symbol.id)
            .filter(Symbol.label.ilike(normalized))
            .first()
            is not None
        )


def _persist_generated_symbol(label: str, language: str, svg_text: str) -> None:
    """Write the image file (PNG when rasterization works, else SVG), create
    the Symbol row, and index it."""
    from src.aac_app.db import get_session
    from src.aac_app.models import Symbol
    from src.aac_app.services.svg_symbol_generator import (
        write_generated_symbol_image,
    )
    from src.aac_app.services.vector_utils import index_symbol

    uploads_dir = config.UPLOADS_DIR / "symbols"
    public_path = write_generated_symbol_image(svg_text, uploads_dir)
    path = uploads_dir / public_path.rsplit("/", 1)[1]

    symbol: Symbol | None = None
    commit_ok = False
    with get_session() as session:
        symbol = Symbol(
            label=label,
            description=f"Auto-generated pictogram for the missing symbol '{label}'.",
            category="general",
            image_path=public_path,
            audio_path=None,
            keywords=label,
            language=language,
            is_builtin=False,
        )
        session.add(symbol)
        try:
            session.commit()
            commit_ok = True
        except Exception:
            session.rollback()
    if not commit_ok or symbol is None:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to persist auto-generated symbol for {label!r}")

    invalidate_generated_today_cache()
    try:
        index_symbol(symbol)
    except Exception as exc:
        logger.warning(
            "Auto-generated symbol for {!r} saved but indexing failed: {}",
            label,
            exc,
        )


def _generate_in_background(key: _PendingKey, label: str, language: str) -> None:
    """Generate + persist one pictogram, then always clear the dedup entry.

    A skipped-but-plausible case (no provider, a symbol that appeared
    meanwhile, or the daily budget exhausted) does not count against the
    word. An actual generation failure records the key in
    ``_recent_failures`` so the provider is not retried until the cooldown
    elapses.

    The budget check + LLM call + persist run under a dedicated lock so the
    daily cap is a *hard* limit: without it, threads spawned in the same
    instant could all read a pre-persist count and overshoot together.
    """
    failed = False
    try:
        # Re-check right before spending an LLM call (race window between the
        # in-memory check and this thread actually running).
        if _has_catalog_symbol(label):
            logger.info(
                "Skip auto-generating {!r}: a catalog symbol appeared meanwhile",
                label,
            )
            return
        with _generation_lock:
            # Hard daily budget stop at spend time: even if the Smartbar's
            # cached flag looked green, never exceed the configured cap of
            # generated symbols for the day. A *fresh* count is required here
            # — the cached budget is TTL-bounded and would let several threads
            # spawned in the same instant all see a zero count and overshoot.
            if _count_generated_today() >= _daily_cap():
                logger.info(
                    "Skip auto-generating {!r}: daily auto-generation budget exhausted",
                    label,
                )
                return
            generate_sync = _generate_sync_callable()
            if generate_sync is None:
                logger.info(
                    "Skip auto-generating {!r}: no LLM provider with sync generation",
                    label,
                )
                return
            from src.aac_app.services.svg_symbol_generator import (
                ShapeSpecError,
                generate_svg_text,
            )

            svg_text = generate_svg_text(label, language, generate_sync)
            _persist_generated_symbol(label, language, svg_text)
            logger.info("Auto-generated SVG symbol for {!r} (lang={})", label, language)
    except ShapeSpecError as exc:
        failed = True
        logger.warning("Could not auto-generate pictogram for {!r}: {}", label, exc)
    except Exception as exc:
        failed = True
        logger.error("Auto-generation of {!r} failed: {}", label, exc)
    finally:
        with _lock:
            _in_flight.discard(key)
            if failed:
                _recent_failures[key] = time.monotonic()


def ensure_symbol_generated(label: str, language: str) -> None:
    """Schedule background SVG generation for a missing symbol (fire-and-forget).

    Cheap, non-blocking, idempotent: a symbol that already exists, is already
    being generated, or whose provider just failed is skipped. Safe to call on
    every Smartbar keystroke.
    """
    normalized = _normalize_label(label)
    if not normalized or not (language or "").strip():
        return
    from src.aac_app.services.runtime_translation import normalize_language_code

    language = normalize_language_code(language) or "en"
    key = _PendingKey(normalized, language)

    # Cheap in-memory budget check (cached count) so the fast path stays
    # non-blocking; the background thread re-checks freshly before the LLM.
    if _daily_budget_remaining() <= 0:
        return

    with _lock:
        if key in _in_flight:
            return
        last_failure = _recent_failures.get(key)
        if last_failure is not None:
            if time.monotonic() - last_failure < _RETRY_COOLDOWN_SECONDS:
                return
            _recent_failures.pop(key, None)
        _in_flight.add(key)

    thread = threading.Thread(
        target=_generate_in_background,
        args=(key, normalized, language),
        name=f"svg-autogen-{normalized[:24]}",
        daemon=True,
    )
    thread.start()


def autogen_enabled() -> bool:
    """True when background generation is allowed.

    On by default so missing catalog words are automatically turned into
    pictograms. Skipped under TESTING=1 (as with the ARASAAC backfill) so
    background threads never touch the real provider in the suite, and
    ``AAC_AUTOGEN_SYMBOLS=0`` (or false/no) disables it entirely for
    environments that want to control LLM cost.
    """
    if os.environ.get("TESTING") == "1":
        return False
    setting = os.environ.get("AAC_AUTOGEN_SYMBOLS", "").strip().lower()
    return setting not in {"0", "false", "no", "off"}


# Daily LLM-cost cap: auto-generation stops for the day after this many
# pictograms. The value lives in the persisted settings (admin-editable as
# ``autogen_daily_cap``) with ``config.AUTOGEN_DAILY_CAP`` as the built-in
# default; 0 disables auto-generation entirely. The count is cached briefly
# so the Smartbar's per-keystroke fast path stays a memory read, while the
# background thread re-queries before spending an LLM call.
_AUTOGEN_DESC_PREFIX = "Auto-generated pictogram"
_generated_today_cache: tuple[float, int] | None = None
_GENERATED_TODAY_TTL_SECONDS = 10.0


def _daily_cap() -> int:
    """Return the configured daily auto-generation cap (>= 0)."""
    try:
        from src.api.deps.settings import get_setting_value

        value = get_setting_value("autogen_daily_cap", "")
        return max(0, int(value)) if value else config.AUTOGEN_DAILY_CAP
    except (TypeError, ValueError) as exc:
        logger.warning("Invalid autogen_daily_cap setting, using default: {}", exc)
        return config.AUTOGEN_DAILY_CAP
    except Exception as exc:
        logger.warning("Could not read autogen_daily_cap setting: {}", exc)
        return config.AUTOGEN_DAILY_CAP


def _count_generated_today(session=None) -> int:
    """Number of auto-generated symbols already persisted today (UTC day)."""
    from datetime import datetime

    from sqlalchemy import func

    from src.aac_app.db import get_session
    from src.aac_app.models import Symbol

    # ``created_at`` is written by SQLAlchemy's ``func.now()`` -> naive UTC
    # in SQLite/Postgres, so the day boundary must be naive UTC as well.
    day_start = datetime.now(UTC).replace(
        tzinfo=None, hour=0, minute=0, second=0, microsecond=0
    )

    def query(db) -> int:
        return (
            db.query(func.count(Symbol.id))
            .filter(
                Symbol.description.like(f"{_AUTOGEN_DESC_PREFIX}%"),
                Symbol.created_at >= day_start,
            )
            .scalar()
            or 0
        )

    if session is not None:
        return query(session)
    with get_session() as session:
        return query(session)


def _daily_budget_remaining() -> int:
    """Cached remaining budget: cap minus today's generated symbols."""
    global _generated_today_cache
    now = time.monotonic()
    with _lock:
        if _generated_today_cache is not None:
            cached_at, count = _generated_today_cache
            if now - cached_at < _GENERATED_TODAY_TTL_SECONDS:
                return max(0, _daily_cap() - count)
    count = _count_generated_today()
    with _lock:
        _generated_today_cache = (now, count)
    return max(0, _daily_cap() - count)


def invalidate_generated_today_cache() -> None:
    """Drop the cached daily count after a persisted symbol mutation."""
    global _generated_today_cache
    with _lock:
        _generated_today_cache = None


def autogen_can_generate() -> bool:
    """True when a pictogram can actually be generated right now.

    Combines the environment switch with the daily cost cap: the Smartbar's
    ``is_generating`` flag must not promise a pictogram when the budget is
    exhausted, or its tiles would spin and poll forever without upgrading.
    """
    if not autogen_enabled():
        return False
    return _daily_budget_remaining() > 0
