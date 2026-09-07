from __future__ import annotations

import re
import threading
import time
from functools import lru_cache

import httpx
from loguru import logger

_TRANSLATION_URL = "https://translate.googleapis.com/translate_a/single"
_TRANSLATION_USER_AGENT = "AAC-Assistant/2.0"

_translation_client_factory = httpx.Client

# Bound every network translation so a slow or unreachable translation
# service can never stall a request for tens of seconds.
_TRANSLATION_TIMEOUT_SECONDS = 3.0
# Bound abandoned daemon workers when the remote service hangs repeatedly.
# A timed-out worker retains its semaphore slot until it exits or the process
# ends, so outages cannot create an unbounded number of live threads/transports.
_TRANSLATION_MAX_CONCURRENCY = 4
_translation_slots = threading.BoundedSemaphore(_TRANSLATION_MAX_CONCURRENCY)
# After this many consecutive failures the translation service is treated
# as unavailable and attempts are skipped for a cooldown period.
_CIRCUIT_BREAK_CONSECUTIVE_FAILURES = 3
_CIRCUIT_BREAK_COOLDOWN_SECONDS = 60.0

_consecutive_failures = 0
_circuit_open_until = 0.0
_circuit_lock = threading.Lock()


# A valid base language code is two or three ASCII letters (ISO 639-1/-2/-3).
# Everything else - punctuation, digits, stray LIKE wildcards such as ``%`` and
# ``_``, or a region tag without a language - is not a code the application
# understands, so it must not survive into the SQL ``LIKE`` patterns that
# consume normalized codes (prediction/analytics regional-language filters).
_BASE_LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}$")


def normalize_language_code(language: str | None) -> str | None:
    """Normalize UI locale tags and provider language values to base codes.

    Accepts ``es``/``en``/``fil``-style base codes plus regional tags such as
    ``es-ES`` or ``en_US`` (the region is dropped). Anything that does not
    resolve to a literal two/three-letter alpha base code returns ``None`` so
    callers fall back to their default instead of feeding garbage (for
    example a ``%`` from an Accept-Language header) into SQL LIKE filters.
    """
    if not language:
        return None
    normalized = language.strip().replace("_", "-")
    if not normalized:
        return None
    base_code = normalized.split("-", 1)[0].lower()
    if not _BASE_LANGUAGE_CODE.match(base_code):
        return None
    return base_code


def normalize_symbol_label(label: str | None) -> str:
    """Canonical case form of a symbol label.

    Single home for the strip + casefold normalization that every symbol
    dedupe/lookup key must use. Python's ``str.lower()`` does NOT fold
    ``straße``/``STRASSE`` (or Greek final sigma) the way ``casefold()`` does,
    so a mixture of ``.lower()`` and ``.casefold()`` call sites made the same
    label dedupe differently depending on the entry path; routing all of them
    through here keeps the keys identical everywhere. Callers that compare in
    SQL must NOT mix this with ``func.lower`` on the column: SQLite ``lower``
    is ASCII-only, so the Python side and the SQL side would disagree for
    accented labels (``ÉCOLE`` vs ``école``) — normalize rows in Python when
    the comparison must be Unicode-correct (see the symbol lookups in
    board_ai.py and the ARASAAC import).
    """
    return (label or "").strip().casefold()


# ---------------------------------------------------------------------------
# SQL LIKE literal-matching helpers.
#
# Single home for escaping LIKE metacharacters, shared by every layer that
# matches user-supplied text with ``LIKE``/``ilike`` (symbol search in
# ``src/api/routers/symbols.py``, topic tokens in prediction_service.py,
# locale attribution from usage logs in ngram_builder.py and pictogram
# de-duplication in symbol_svg_autogen.py). Keeping one copy prevents the
# identical helpers from drifting apart again.
# ---------------------------------------------------------------------------

# Marker that neutralizes LIKE wildcards. Passed as ``escape=`` on every
# ``.like``/``.ilike`` call that consumes an escaped pattern.
LIKE_ESCAPE = "\\"


def escape_like_literal(text: str) -> str:
    """Escape LIKE metacharacters so ``text`` matches literally.

    Backslashes are doubled first so an input backslash cannot neutralize the
    escape marker; ``%`` and ``_`` are then escaped, turning them into literal
    characters instead of wildcards.
    """
    escaped = text.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
    return escaped.replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")


def contains_like_pattern(text: str) -> str:
    """Build a case-folded ``%...%`` substring pattern for a literal string.

    Uses the canonical ``casefold()`` (not ``lower()``): the symbol dedupe
    paths treat ``ß == ss`` and ``İ == i̇``, so a search built with plain
    ``lower()`` would miss stored labels that casefold equal to the query.
    (The LIKE comparison itself stays ASCII-faithful per character; this
    folding only normalizes the query text before escaping.)

    The text is stripped first, mirroring ``normalize_symbol_label``'s strip:
    a search with accidental padding (copy/paste, mobile keyboards) must not
    miss the exact label the catalog holds.

    NOTE the real contract: after the internal strip, an empty input maps to
    ``"%%"`` — a match-all. Callers MUST strip their query text before the
    truthiness guard and never feed this helper blank/whitespace text; a
    whitespace-only query reaching SQL as ``"%%"`` would silently list the
    whole table. Every search route (learning.py, symbols.py, boards.py)
    strips before deciding whether to search at all.
    """
    return f"%{escape_like_literal(text.strip()).casefold()}%"


def unicode_recall_ids(
    db,
    model,
    columns,
    text: str,
) -> list[int]:
    """Return ids whose stored text casefolds-contains ``text``.

    Shared unicode-recall net for the search routes (symbol label/descrip-
    tion/keywords, the keywords standalone filter, board names). SQL
    ``lower()``/``ilike`` never folds ``ß``/``İ`` the way Python ``casefold()``
    does, so a stored ``straße`` row is invisible to ``LIKE '%STRASSE%'`` on
    both backends. This helper scans the given columns in Python and returns
    the small id set whose casefolded text contains the casefolded query —
    the exact recall SQL cannot express.

    Callers gate on their SQL filter returning NOTHING first (recall matters
    only on empty results); this helper is then the O(catalog) fallback. An
    "ASCII fast path" is deliberately NOT used: the fold gap lives in the
    STORED text as well as the query, so an all-caps query (``STRASSE``)
    against a stored ``straße`` has ``query.casefold() == query.lower()`` yet
    still needs the scan (see the committed D7 test in
    tests/test_prompt20_regressions.py). Any scan error must degrade to an
    empty recall set at the call site, never a 500.

    The scan is deliberately NOT row-capped: rows stream through
    ``yield_per`` so memory stays bounded, and truncating at an arbitrary
    row count would silently miss a fold-only match stored beyond it (the
    ARASAAC auto-import alone seeds ~17k symbols). The cost is acceptable
    because callers invoke this only after SQL showed nothing.
    """
    stripped = (text or "").strip()
    if not stripped:
        return []
    folded = stripped.casefold()
    ids: list[int] = []
    for row_id, *values in db.query(model.id, *columns).yield_per(500):
        # Values are compared in Python (where the fold happens) so NULL
        # columns simply never match — do NOT pre-filter with ``IS NOT NULL``
        # per column: AND-ing them would drop every row that leaves one of
        # the searched columns empty (a label row without a description).
        for value in values:
            if isinstance(value, str) and folded in value.casefold():
                ids.append(row_id)
                break
    return ids


def _translate_worker(text: str, target_lang: str) -> str:
    """Translate through Google's bounded JSON endpoint.

    The client is created per call so the worker owns and closes its transport;
    this keeps the existing hard timeout safe even when a request hangs.
    """
    with _translation_client_factory(
        timeout=httpx.Timeout(_TRANSLATION_TIMEOUT_SECONDS),
        follow_redirects=False,
        headers={"User-Agent": _TRANSLATION_USER_AGENT},
    ) as client:
        response = client.get(
            _TRANSLATION_URL,
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": target_lang,
                "dt": "t",
                "q": text,
            },
        )
        response.raise_for_status()
        payload = response.json()

    try:
        translated = "".join(
            str(segment[0])
            for segment in payload[0]
            if isinstance(segment, list) and segment and segment[0]
        ).strip()
    except (IndexError, TypeError, KeyError) as exc:
        raise RuntimeError("invalid translation response") from exc
    if not translated:
        raise RuntimeError("empty translation result")
    return translated


@lru_cache(maxsize=4096)
def _translate_cached(text: str, target_lang: str) -> str:
    """Translate with a hard timeout and bounded worker concurrency.

    Only successes are cached; failures raise so a later request can retry
    once the service recovers. A fresh daemon thread is used per call so a
    hung translation can never block the request or interpreter shutdown.
    The semaphore prevents repeated hangs from creating unbounded workers.
    """
    if not _translation_slots.acquire(blocking=False):
        # Do not make request handlers wait behind already-hung workers.
        raise TimeoutError("translation worker capacity exhausted")

    result_holder: dict = {}

    def run() -> None:
        try:
            result_holder["value"] = _translate_worker(text, target_lang)
        except Exception as exc:  # capture for the caller
            result_holder["error"] = exc
        finally:
            _translation_slots.release()

    worker = threading.Thread(
        target=run,
        name="aac-translate",
        daemon=True,
    )
    try:
        worker.start()
    except BaseException:
        # A failed thread start cannot execute ``run`` and release the slot.
        _translation_slots.release()
        raise
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


def translate_text(text: str | None, target_lang: str | None) -> str | None:
    """Translate text through the configured runtime service.

    Results are cached per label/language, each network call is bounded by a
    short timeout, and a circuit breaker fails fast while the service is
    unreachable. Callers must surface that failure instead of using source text
    as a false translation.
    """
    normalized_target = normalize_language_code(target_lang)
    if not text or not normalized_target:
        return text
    if _translation_disabled():
        raise RuntimeError("Runtime translation is temporarily unavailable")

    try:
        translated = _translate_cached(text, normalized_target)
    except Exception as exc:
        _note_failure()
        logger.warning(f"Translation failed for {text!r}: {exc}")
        raise RuntimeError("Runtime translation failed") from exc
    _note_success()
    return translated
