import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import RLock
from weakref import WeakKeyDictionary

from loguru import logger
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import BoardSymbol, Symbol, SymbolUsageLog
from ..services.runtime_translation import normalize_language_code
from ..services.symbol_analytics import SymbolAnalytics
from ..services.symbol_catalog import category_is_noun, standard_library_labels

# Labels matching these patterns are internal dev artifacts — never suggest them.
_BAD_LABEL_SUBSTRINGS: tuple[str, ...] = (
    "frontend-",
    "comm-",
    "node_modules",
    "dist/",
    "build/",
    "src-",
)


def _label_looks_bad(label: str) -> bool:
    """True when a label is clearly an internal path/id, not a real symbol."""
    lower = (label or "").strip().lower()
    if not lower:
        return True
    if len(lower) > 50:
        return True
    if any(p in lower for p in _BAD_LABEL_SUBSTRINGS):
        return True
    if "/" in lower or "\\" in lower:
        return True
    # More than 3 hyphens is almost certainly a path/id, not a word.
    return lower.count("-") > 3


# Common stop-words excluded from topic tokenization so a topic like
# "Inteligencia Artificial y LLMs" focuses on inteligencia/artificial/llms.
_TOPIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "y", "o", "e", "u", "de", "del", "la", "el", "las", "los", "en",
        "the", "and", "or", "of", "for", "with", "a", "an", "to", "in",
        "on", "about",
    }
)


def _tokenize_topic(topic: str) -> list[str]:
    r"""Split a topic string into meaningful lowercase tokens (len >= 2).

    Splits on any non-alphanumeric character (Unicode-aware via ``\W``)
    so accented words like "inteligencia" survive intact.
    """
    import re

    tokens: list[str] = []
    for raw in re.split(r"\W+", topic, flags=re.UNICODE):
        word = (raw or "").strip().lower()
        if len(word) < 2 or word in _TOPIC_STOPWORDS:
            continue
        tokens.append(word)
    # Deduplicate preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for word in tokens:
        if word not in seen:
            seen.add(word)
            unique.append(word)
    return unique

# Punctuation appended after all real suggestions (only when they fit).
PUNCTUATION: tuple[str, ...] = (".", ",", "?", "!")

# A topic-word provider maps (language, topic) to a list of category words.
# It is optional: when the catalog cannot cover the topic, the router supplies
# an LLM-backed callable so learners are never limited by the symbol database.
TopicWordFetcher = Callable[[str, str], list[str]]

# LLM topic-word fetch is cached per (language, normalized topic) so repeated
# keystrokes in the Smartbar do not re-call the provider. TTL bounds staleness
# without ever re-generating on every prediction request.
_TOPIC_WORD_TTL_SECONDS = 60 * 60
_topics_word_cache: dict[tuple[str, str], tuple[float, tuple[str, ...]]] = {}
_topics_word_lock = RLock()


def _cached_topic_words(
    language: str, topic: str, fetcher: TopicWordFetcher
) -> tuple[str, ...]:
    """Return topic words, generating once per (language, topic)."""
    normalized_topic = (topic or "").strip().casefold()
    if not normalized_topic:
        return ()
    key = (language, normalized_topic)
    now = time.monotonic()
    with _topics_word_lock:
        cached = _topics_word_cache.get(key)
        if cached is not None and now - cached[0] < _TOPIC_WORD_TTL_SECONDS:
            return cached[1]
    try:
        words = fetcher(language, topic) or []
    except Exception as exc:
        logger.warning("Topic word generation failed: {}", exc)
        words = []
    result = tuple(
        dict.fromkeys(
            word.strip() for word in words if word and not _label_looks_bad(word)
        )
    )
    with _topics_word_lock:
        _topics_word_cache[key] = (now, result)
    return result


@dataclass(frozen=True)
class _SymbolCatalogEntry:
    """Detached, immutable symbol data safe to retain between requests."""

    id: int
    label: str
    category: str | None
    image_path: str | None
    language: str | None


_catalog_lock = RLock()
_catalog_generation = 0
_catalog_cache: WeakKeyDictionary[Engine, dict[str, tuple[_SymbolCatalogEntry, ...]]] = (
    WeakKeyDictionary()
)


def clear_prediction_cache() -> None:
    """Invalidate cached symbol catalogs after any symbol mutation."""
    global _catalog_generation
    with _catalog_lock:
        _catalog_generation += 1
        _catalog_cache.clear()


def _invalidate_after_symbol_change(*_args) -> None:
    clear_prediction_cache()


# Mapper events cover API routes, seed/import paths, and direct service writes in
# one place, avoiding a fragile list of cache-invalidation call sites.
event.listen(Symbol, "after_insert", _invalidate_after_symbol_change)
event.listen(Symbol, "after_update", _invalidate_after_symbol_change)
event.listen(Symbol, "after_delete", _invalidate_after_symbol_change)


class _PredictionContext:
    """Per-request state and helpers for the five suggestion tiers.

    Kept in one object so the tier methods read the same mutable state the
    original single-function implementation shared through closures.
    """

    def __init__(
        self,
        *,
        user_id: int,
        current_symbols: list[dict],
        language: str,
        offset: int,
        base_limit: int,
        limit: int,
        board_id: int | None,
        db: Session | None,
        analytics_service: SymbolAnalytics,
        load_model: Callable[[str], dict],
        topic: str | None = None,
        topic_word_fetcher: TopicWordFetcher | None = None,
        content_policy=None,
    ) -> None:
        self.user_id = user_id
        self.current_symbols = current_symbols
        self.language = language
        self.offset = offset
        self.base_limit = base_limit
        self.limit = limit
        self.board_id = board_id
        self.db = db
        self.analytics_service = analytics_service
        self._load_model = load_model
        # Topic tokens drive a topic-aware tier so predictions reflect the
        # subject under study instead of always surfacing the same global
        # standard-library fallbacks. The fetcher, when supplied, generates
        # topic vocabulary beyond the catalog so learners are not limited by
        # the symbols present in the database.
        self.topic = topic or ""
        self.topic_tokens = _tokenize_topic(topic or "")
        self.topic_word_fetcher = topic_word_fetcher
        # Resolved content-safety policy (None = feature not wired for this
        # request, e.g. warmup). Gates topic words and pictogram scheduling.
        self.content_policy = content_policy

        self.suggestions: list[dict] = []
        self.seen_labels: set[str] = set()

        self.lang = normalize_language_code(language) or "en"
        self.preferred_langs = [self.lang]

        self.allowed_symbol_ids: set[int] | None = None
        if board_id is not None:
            self._resolve_allowed_symbol_ids()
            # A requested board that has no visible symbols is still a valid
            # empty scope. Keep it distinct from a missing/failed scope so
            # global tiers cannot leak unrelated suggestions.
            if self.allowed_symbol_ids is None:
                self.allowed_symbol_ids = set()

    def _resolve_allowed_symbol_ids(self) -> None:
        """Load the visible symbol ids of the board scope, if any."""
        try:
            ids = None
            if self.db is not None:
                ids = self._board_symbol_ids(self.db)
            else:
                with get_session() as session:
                    ids = self._board_symbol_ids(session)
            if ids is not None:
                self.allowed_symbol_ids = {sid for sid in ids if sid is not None}
        except Exception as exc:
            logger.warning(
                "Failed to resolve board symbols for board_id={}: {}",
                self.board_id,
                exc,
            )
            self.allowed_symbol_ids = set()

    def _board_symbol_ids(self, session: Session) -> list[int]:
        rows = (
            session.query(BoardSymbol.symbol_id)
            .filter(
                BoardSymbol.board_id == self.board_id,
                BoardSymbol.is_visible == True,  # noqa: E712
                BoardSymbol.symbol_id.isnot(None),
            )
            .all()
        )
        return [row[0] for row in rows]

    def normalize_label(self, label: str) -> str:
        return (label or "").strip().lower()

    def language_rank(self, language_code: str | None) -> int:
        normalized = normalize_language_code(language_code)
        try:
            return self.preferred_langs.index(normalized)
        except ValueError:
            return len(self.preferred_langs) + 1

    def localize_label(self, label: str, symbol_language: str | None) -> str:
        """Return a label only when its symbol belongs to the requested locale.

        Runtime translation is deliberately not used for suggestions: a
        translated label can still point at an image from the source locale.
        The catalog must provide the locale-specific symbol record instead.
        """
        return label if normalize_language_code(symbol_language) == self.lang else ""

    def add_symbol(
        self,
        *,
        symbol_id: int,
        label: str,
        category: str | None,
        image_path: str | None,
        confidence: float,
        source: str,
        symbol_language: str | None = None,
    ) -> None:
        if len(self.suggestions) >= self.base_limit:
            return
        if (
            self.allowed_symbol_ids is not None
            and symbol_id > 0
            and symbol_id not in self.allowed_symbol_ids
        ):
            return
        # Skip labels that are clearly internal paths/dev artifacts.
        if _label_looks_bad(label):
            return
        localized_label = self.localize_label(label, symbol_language)
        if not localized_label:
            return
        normalized_label = self.normalize_label(localized_label)
        if not normalized_label or normalized_label in self.seen_labels:
            return
        self.suggestions.append(
            {
                "symbol_id": symbol_id,
                "label": localized_label,
                "category": category,
                "image_path": image_path,
                "confidence": confidence,
                "source": source,
            }
        )
        self.seen_labels.add(normalized_label)

    def get_symbol_buckets(self) -> dict[str, tuple[_SymbolCatalogEntry, ...]]:
        """Return a process-local catalog keyed to the owning DB engine.

        Only detached immutable values are retained, so cached entries do
        not keep ORM sessions alive. Mapper events clear the catalog after
        inserts, updates, and deletes; the weak engine keys avoid retaining
        test or short-lived engines.
        """

        def load(session: Session) -> dict[str, tuple[_SymbolCatalogEntry, ...]]:
            bind = session.get_bind()
            while True:
                with _catalog_lock:
                    cached = _catalog_cache.get(bind)
                    if cached is not None:
                        return cached
                    query_generation = _catalog_generation

                # Keep ORM objects and the catalog lock out of the hot path.
                # The catalog only needs five scalar columns, and yield_per
                # avoids materializing every Symbol instance at once.
                rows = (
                    session.query(
                        Symbol.id,
                        Symbol.label,
                        Symbol.category,
                        Symbol.image_path,
                        Symbol.language,
                    )
                    .filter(Symbol.label.isnot(None))
                    .yield_per(1000)
                )
                buckets: dict[str, list[_SymbolCatalogEntry]] = {}
                for row in rows:
                    key = self.normalize_label(row.label)
                    if not key:
                        continue
                    buckets.setdefault(key, []).append(
                        _SymbolCatalogEntry(
                            id=row.id,
                            label=row.label,
                            category=row.category,
                            image_path=row.image_path,
                            language=row.language,
                        )
                    )
                frozen = {key: tuple(entries) for key, entries in buckets.items()}

                # Do not publish a snapshot that raced a symbol mutation.
                # A concurrent mutation invalidates and retries this query.
                with _catalog_lock:
                    cached = _catalog_cache.get(bind)
                    if cached is not None:
                        return cached
                    if query_generation != _catalog_generation:
                        continue
                    _catalog_cache[bind] = frozen
                    return frozen

        if self.db is not None:
            return load(self.db)
        with get_session() as session:
            return load(session)

    def best_symbol(
        self, options: Sequence[_SymbolCatalogEntry]
    ) -> _SymbolCatalogEntry:
        """Pick the preferred language match, then lowest ID for ties."""
        return sorted(
            options,
            key=lambda sym: (
                self.language_rank(getattr(sym, "language", None)),
                sym.id,
            ),
        )[0]

    def resolve_symbols_by_labels(
        self, labels: Sequence[str]
    ) -> list[tuple[_SymbolCatalogEntry, str]]:
        wanted = [
            self.normalize_label(label)
            for label in labels
            if self.normalize_label(label)
        ]
        if not wanted:
            return []

        buckets = self.get_symbol_buckets()
        resolved: list[tuple[_SymbolCatalogEntry, str]] = []
        for wanted_label in wanted:
            options = buckets.get(wanted_label, [])
            if not options:
                continue
            if self.allowed_symbol_ids is not None:
                options = [o for o in options if o.id in self.allowed_symbol_ids]
                if not options:
                    continue
            resolved.append((self.best_symbol(options), wanted_label))
        return resolved

    def resolve_symbol_for_label(self, label: str) -> _SymbolCatalogEntry | None:
        # Normalized bucket lookup replaces the former per-label ``ilike``
        # query: labels containing LIKE wildcards (%, _) are now matched
        # literally, and non-ASCII labels fold case Unicode-aware instead
        # of ASCII-only. Both are intentional correctness improvements.
        normalized_label = self.normalize_label(label)
        if not normalized_label:
            return None
        options = self.get_symbol_buckets().get(normalized_label, [])
        if self.allowed_symbol_ids is not None:
            options = [o for o in options if o.id in self.allowed_symbol_ids]
        if not options:
            return None
        return self.best_symbol(options)

    # -- suggestion tiers ---------------------------------------------------

    def suggest_topic(self) -> None:
        """Tier 0: symbols whose label/keywords overlap the session topic.

        Runs before any fallback so a study topic like "Inteligencia
        Artificial y LLMs" surfaces the matching catalog symbols instead
        of the same global standard-library words on every topic.
        """
        if not self.topic_tokens:
            return
        from sqlalchemy import func, or_

        # Build OR conditions: each token is matched against label/keywords
        # via word boundaries. LIKE is portable across SQLite/Postgres.
        clauses: list = []
        for token in self.topic_tokens:
            like_tok = f"% {token}%"
            clauses.extend(
                [
                    func.lower(Symbol.label).like(f"{token}%"),
                    func.lower(Symbol.label).like(like_tok),
                    func.lower(Symbol.keywords).like(f"%{token}%"),
                ]
            )
        if not clauses:
            return

        def run_query(session: Session) -> list:
            q = session.query(
                Symbol.id,
                Symbol.label,
                Symbol.category,
                Symbol.image_path,
                Symbol.language,
                Symbol.keywords,
            ).filter(
                Symbol.label.isnot(None),
                or_(*clauses),
            )
            # Restrict to the active locale so a Spanish topic does not
            # surface English-only symbols, and vice versa.
            q = q.filter(
                or_(
                    func.lower(Symbol.language) == self.lang,
                    func.lower(Symbol.language).like(f"{self.lang}-%"),
                )
            )
            if self.allowed_symbol_ids is not None:
                q = q.filter(Symbol.id.in_(self.allowed_symbol_ids))
            # Bounded scan; the matching catalog slice is small.
            return q.limit(max(self.base_limit * 4, 60)).all()

        try:
            rows = run_query(self.db) if self.db is not None else None
            if rows is None:
                with get_session() as session:
                    rows = run_query(session)
        except Exception as exc:
            logger.warning("Topic symbol query failed: {}", exc)
            return

        def _word_boundary_hit(text: str, token: str) -> bool:
            """True when ``token`` appears as a whole word in ``text``."""
            return bool(re.search(rf"(^|\W){re.escape(token)}($|\W)", text))

        def score(label: str, keywords: str | None) -> tuple[int, int]:
            """Rank a symbol for the topic: (label hits, keyword hits).

            Whole-word label matches are worth 3, token-prefix label matches
            (e.g. "artificial" vs "fuegos artificiales") 1; keyword hits are
            worth 2 (whole word) or 1 (anywhere). Sorting is lexicographic on
            ``(-label_hits, -keyword_hits)`` so a label that actually contains
            the topic words always outranks one that merely embeds a token.
            """
            label_lower = (label or "").lower()
            keyword_lower = (keywords or "").lower()
            label_hits = 0
            keyword_hits = 0
            for token in self.topic_tokens:
                if _word_boundary_hit(label_lower, token):
                    label_hits += 3
                elif label_lower.startswith(token) or token in label_lower:
                    label_hits += 1
                if keyword_lower:
                    if _word_boundary_hit(keyword_lower, token):
                        keyword_hits += 2
                    elif token in keyword_lower:
                        keyword_hits += 1
            return label_hits, keyword_hits

        def topic_key(row):
            label_hits, keyword_hits = score(row[1] or "", row[5])
            return (
                -label_hits,
                -keyword_hits,
                # Shorter labels win ties: a phrase matching the whole topic
                # outranks a long label that merely happens to embed a token.
                len(row[1] or ""),
            )

        ranked = sorted(rows, key=topic_key)
        for sid, label, cat, img, language_code, _kw in ranked:
            self.add_symbol(
                symbol_id=sid,
                label=label,
                category=cat,
                image_path=img,
                confidence=0.6,
                source="topic",
                symbol_language=language_code,
            )

    def suggest_topic_words(self) -> None:
        """Tier 0b: LLM-generated words filling whatever the catalog missed.

        Keys off the same topic as ``suggest_topic`` and fills the remaining
        slots when the catalog did not fully cover the topic: a learner
        asking about a subject outside the symbol database still gets usable
        vocabulary. Each word is first matched against the catalog so an
        existing symbol wins (image attached); any word without a symbol is
        surfaced as a text-only suggestion so the user is never limited by
        the database.

        The tier keeps running while the catalog only *partially* covers the
        topic: once the first generated pictogram lands in the catalog,
        ``suggest_topic`` produces some symbols, but the still-pending topic
        words must keep appearing so their tiles upgrade in place instead of
        vanishing mid-generation. The LLM fetch itself stays cached per
        (language, topic), and a fully-covered topic (catalog tier already at
        the limit) still skips it entirely.
        """
        if not self.topic_tokens or self.topic_word_fetcher is None:
            return
        # The catalog tier already filled the slots; nothing to add.
        if len(self.suggestions) >= self.base_limit:
            return
        words = _cached_topic_words(self.lang, self.topic, self.topic_word_fetcher)
        # Layered content safety: never surface or schedule a topic word the
        # student's effective policy blocks (and never spend LLM tokens on it).
        if self.content_policy is not None:
            from src.aac_app.services.content_safety import check_text, log_event

            filtered: list[str] = []
            for candidate in words:
                verdict = check_text(self.content_policy, candidate)
                if verdict.blocked:
                    log_event(
                        user_id=self.user_id,
                        surface="words",
                        direction="output",
                        verdict="blocked",
                        matched=list(verdict.matched_terms),
                        detail=f"topic word: {candidate[:200]}",
                        db=self.db,
                    )
                else:
                    filtered.append(candidate)
            words = filtered
        for word in words:
            if len(self.suggestions) >= self.base_limit:
                break
            normalized = self.normalize_label(word)
            if not normalized or normalized in self.seen_labels:
                continue
            # Re-attach a catalog symbol when one exists (image preferred).
            entry = self.resolve_symbol_for_label(word)
            if entry is not None:
                self.add_symbol(
                    symbol_id=entry.id,
                    label=entry.label,
                    category=entry.category,
                    image_path=entry.image_path,
                    confidence=0.7,
                    source="ai",
                    symbol_language=entry.language,
                )
                continue
            # No symbol: emit a text-only suggestion. Board-scoped requests
            # must not leak words outside their scope, so this fallback only
            # applies when no board restricts the vocabulary. Meanwhile the
            # pictogram is generated in the background (once per word) so a
            # later request resolves it as a real symbol with an image.
            if self.allowed_symbol_ids is not None:
                continue
            fake_id = -(abs(hash(normalized)) % 1000000)
            # ``is_generating`` tells the frontend a pictogram is being made
            # in the background, so it can show a "generating" state and
            # auto-refresh — the tile upgrades to the real image when done.
            self.suggestions.append(
                {
                    "symbol_id": fake_id,
                    "label": word,
                    "category": None,
                    "image_path": None,
                    "confidence": 0.7,
                    "source": "ai",
                    "is_text_only": True,
                    "is_generating": self._is_svg_generation_enabled(),
                }
            )
            self.seen_labels.add(normalized)
            self._schedule_svg_generation(word)

    def suggest_history(self) -> None:
        """Tier 1: personalized suggestions from the user's usage history."""
        history_suggestions = self.analytics_service.suggest_next_symbol(
            user_id=self.user_id,
            symbols=self.current_symbols,
            limit=max(self.base_limit, 5),
            db=self.db,
        )
        for suggestion in history_suggestions:
            self.add_symbol(
                symbol_id=suggestion.get("symbol_id"),
                label=suggestion.get("label"),
                category=suggestion.get("category"),
                image_path=suggestion.get("image_path"),
                confidence=float(suggestion.get("confidence", 0.5)),
                source="history",
                symbol_language=suggestion.get("language"),
            )

    def suggest_ngrams(self) -> None:
        """Tier 2: bundled static N-gram model when history left room."""
        if len(self.suggestions) >= self.base_limit or not self.current_symbols:
            return
        model = self._load_model(self.language)
        bigrams = model.get("bigrams", {})
        if not bigrams:
            return
        last_symbol_label = (
            self.current_symbols[-1].get("label", "").lower()
            if self.current_symbols
            else ""
        )
        if not last_symbol_label or last_symbol_label not in bigrams:
            return
        next_word_probs = bigrams[last_symbol_label]
        sorted_words = sorted(
            next_word_probs.items(), key=lambda item: item[1], reverse=True
        )
        for word, _probability in sorted_words:
            if len(self.suggestions) >= self.base_limit:
                break
            if self.normalize_label(word) in self.seen_labels:
                continue
            symbol_obj = self.resolve_symbol_for_label(word)
            if symbol_obj:
                self.add_symbol(
                    symbol_id=symbol_obj.id,
                    label=symbol_obj.label,
                    category=symbol_obj.category,
                    image_path=symbol_obj.image_path,
                    confidence=0.4,
                    source="general_model",
                    symbol_language=symbol_obj.language,
                )

    def suggest_popular_symbols(self) -> None:
        """Tier 3: most-popular global symbols, interleaving nouns and others."""
        if len(self.suggestions) >= self.base_limit:
            return
        try:
            popular_suggestions = self.analytics_service.suggest_next_symbol(
                user_id=self.user_id,
                symbols=[],
                limit=max(self.base_limit * 2, 10),  # Request more to filter
                db=self.db,
            )

            # An empty analytics result is a valid cold-start result; the
            # standard library is handled by its own explicit tier below.
            if not popular_suggestions:
                return

            # Split popular candidates into nouns and others to mix them.
            noun_candidates = []
            other_candidates = []
            for suggestion in popular_suggestions:
                if category_is_noun(suggestion.get("category")):
                    noun_candidates.append(suggestion)
                else:
                    other_candidates.append(suggestion)

            # Interleave or prioritize nouns if we have few.
            while len(self.suggestions) < self.base_limit and (
                noun_candidates or other_candidates
            ):
                if noun_candidates:
                    suggestion = noun_candidates.pop(0)
                    self.add_symbol(
                        symbol_id=suggestion.get("symbol_id"),
                        label=suggestion.get("label"),
                        category=suggestion.get("category"),
                        image_path=suggestion.get("image_path"),
                        confidence=0.15,
                        source="popular",
                        symbol_language=suggestion.get("language"),
                    )
                if len(self.suggestions) >= self.base_limit:
                    break
                if other_candidates:
                    suggestion = other_candidates.pop(0)
                    self.add_symbol(
                        symbol_id=suggestion.get("symbol_id"),
                        label=suggestion.get("label"),
                        category=suggestion.get("category"),
                        image_path=suggestion.get("image_path"),
                        confidence=0.1,
                        source="popular",
                        symbol_language=suggestion.get("language"),
                    )
        except Exception as exc:
            raise RuntimeError("Popular symbol prediction failed") from exc

    def suggest_standard_library(self) -> None:
        """Tier 4 (cold start): standard-library labels from the catalog."""
        if len(self.suggestions) >= self.base_limit:
            return
        resolved = self.resolve_symbols_by_labels(
            standard_library_labels(self.lang)
        )
        for sym, _ in resolved:
            self.add_symbol(
                symbol_id=sym.id,
                label=sym.label,
                category=sym.category,
                image_path=sym.image_path,
                confidence=0.25,
                source="standard_library",
                symbol_language=sym.language,
            )

    def suggest_board_library(self) -> None:
        """Tier 5: board-scoped fallbacks (personal, popular, then layout)."""
        if (
            self.allowed_symbol_ids is None
            or len(self.suggestions) >= self.base_limit
        ):
            return
        try:
            from sqlalchemy import desc, func

            def fill_board_library(session: Session) -> None:
                self._board_personal(session, desc, func)
                if len(self.suggestions) < self.base_limit:
                    self._board_popular(session, desc, func)
                if len(self.suggestions) < self.base_limit and self.board_id is not None:
                    self._board_layout(session)

            if self.db is not None:
                fill_board_library(self.db)
            else:
                with get_session() as session:
                    fill_board_library(session)
        except Exception as exc:
            raise RuntimeError("Board symbol prediction failed") from exc

    def _board_usage_symbols(
        self,
        session: Session,
        desc,
        func,
        *,
        user_id: int | None,
        confidence: float,
        source: str,
    ) -> None:
        """Fill suggestions from board symbols ranked by usage.

        ``user_id`` restricts to the user's own usage (personal tier);
        ``None`` ranks by global usage (popular tier). The two tiers differ
        only in that filter plus their confidence and source labels.
        """
        query = (
            session.query(
                Symbol.id,
                Symbol.label,
                Symbol.category,
                Symbol.image_path,
                Symbol.language,
                func.count(SymbolUsageLog.id).label("cnt"),
            )
            .join(SymbolUsageLog, SymbolUsageLog.symbol_id == Symbol.id)
            .filter(Symbol.id.in_(self.allowed_symbol_ids))
        )
        if user_id is not None:
            query = query.filter(SymbolUsageLog.user_id == user_id)
        query = (
            query.group_by(
                Symbol.id,
                Symbol.label,
                Symbol.category,
                Symbol.image_path,
                Symbol.language,
            )
            .order_by(desc("cnt"))
            .limit(max(self.base_limit * 2, 10))
        )
        for sid, label, cat, img, language_code, _cnt in query.all():
            self.add_symbol(
                symbol_id=sid,
                label=label,
                category=cat,
                image_path=img,
                confidence=confidence,
                source=source,
                symbol_language=language_code,
            )

    def _board_personal(self, session: Session, desc, func) -> None:
        self._board_usage_symbols(
            session,
            desc,
            func,
            user_id=self.user_id,
            confidence=0.35,
            source="board_personal",
        )

    def _board_popular(self, session: Session, desc, func) -> None:
        self._board_usage_symbols(
            session,
            desc,
            func,
            user_id=None,
            confidence=0.22,
            source="board_popular",
        )

    def _board_layout(self, session: Session) -> None:
        placed = (
            session.query(
                BoardSymbol.symbol_id,
                Symbol.label,
                Symbol.category,
                Symbol.image_path,
                Symbol.language,
                BoardSymbol.position_y,
                BoardSymbol.position_x,
            )
            .join(Symbol, Symbol.id == BoardSymbol.symbol_id)
            .filter(
                BoardSymbol.board_id == self.board_id,
                BoardSymbol.is_visible == True,  # noqa: E712
                BoardSymbol.symbol_id.isnot(None),
            )
            .order_by(BoardSymbol.position_y, BoardSymbol.position_x)
            .all()
        )
        seen_ids: set[int] = set()
        for sid, label, cat, img, language_code, _, _ in placed:
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            self.add_symbol(
                symbol_id=sid,
                label=label,
                category=cat,
                image_path=img,
                confidence=0.18,
                source="board_layout",
                symbol_language=language_code,
            )

    def _is_svg_generation_enabled(self) -> bool:
        """True when background pictogram generation may run right now.

        Includes the daily cost cap: when the auto-generation budget for the
        day is exhausted the flag goes False, so the Smartbar shows the static
        letter tile instead of a spinner that would never resolve.
        """
        try:
            from src.aac_app.services.symbol_svg_autogen import (
                autogen_can_generate,
            )

            return autogen_can_generate()
        except Exception as exc:
            logger.warning("Could not check SVG autogen flag: {}", exc)
            return False

    def _schedule_svg_generation(self, word: str) -> None:
        """Fire-and-forget background pictogram generation for a missing word.

        Idempotent and non-blocking: dedup and thread spawning happen under
        a cheap in-memory lock, so the Smartbar response latency is unaffected
        and a symbol is generated at most once per (label, language). The
        topic is forwarded as disambiguation context so homonyms resolve to
        the meaning that fits the learner's current theme ("sierra" ->
        mountains in a geography topic, a saw in a tools topic).
        """
        try:
            from src.aac_app.services.content_safety import (
                check_text,
                log_event,
            )
            from src.aac_app.services.symbol_svg_autogen import (
                ensure_symbol_generated,
            )

            if not self._is_svg_generation_enabled():
                return
            if self.content_policy is not None:
                label_verdict = check_text(self.content_policy, word)
                if label_verdict.blocked:
                    log_event(
                        user_id=self.user_id,
                        surface="pictogram",
                        direction="output",
                        verdict="blocked",
                        matched=list(label_verdict.matched_terms),
                        detail=f"autogen label: {word[:200]}",
                        db=self.db,
                    )
                    return
            ensure_symbol_generated(word, self.lang, context=self.topic or None)
        except Exception as exc:
            logger.warning(
                "Could not schedule SVG generation for {!r}: {}", word, exc
            )

    def suggest_punctuation(self) -> None:
        """Tier 6: punctuation, only when it fits the remaining budget."""
        if self.offset != 0:
            return
        for punct in PUNCTUATION:
            if len(self.suggestions) >= self.limit:
                break
            if self.normalize_label(punct) in self.seen_labels:
                continue
            fake_id = -(abs(hash(punct)) % 1000000)
            self.suggestions.append(
                {
                    "symbol_id": fake_id,
                    "label": punct,
                    "category": "punctuation",
                    "image_path": None,
                    "confidence": 1.0,
                    "source": "punctuation",
                }
            )
            self.seen_labels.add(self.normalize_label(punct))


class PredictionService:
    """
    Lightweight, multilanguage next-word prediction engine.
    Combines user usage history with bundled static N-grams.
    Replaces heavy LLM calls for symbol suggestion.
    """

    _instance = None
    _models: dict[str, dict] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.analytics_service = SymbolAnalytics()
        return cls._instance

    def warmup(self, db: Session | None = None) -> None:
        """Build the symbol catalog off the request path.

        The first prediction request otherwise pays a one-time full-catalog
        scan (the result is cached per engine afterwards). Warming it in the
        background at startup makes Smartbar suggestions start instantly.
        N-gram JSON models are deliberately left lazy: they are small, and
        loading them here could race the periodic rebuild (which writes the
        files in place) and permanently cache an empty model. Safe to call
        repeatedly: the catalog is cached after the first build.
        """
        try:
            _PredictionContext(
                user_id=0,
                current_symbols=[],
                language="en",
                offset=0,
                base_limit=1,
                limit=1,
                board_id=None,
                db=db,
                analytics_service=self.analytics_service,
                load_model=self._load_model,
            ).get_symbol_buckets()
        except Exception as exc:
            logger.warning("Prediction warmup failed to build symbol catalog: {}", exc)

    def _load_model(self, language_code: str) -> dict:
        """Load static N-gram model for the given language."""
        lang = normalize_language_code(language_code) or "en"

        if lang in self._models:
            return self._models[lang]

        try:
            # Use frozen-aware path from config. A model rebuilt from real
            # usage logs lives in the writable data/ngrams directory and
            # takes precedence over the bundled hand-written seed.
            from src import config
            rebuilt_path = config.get_data_path("ngrams") / f"{lang}.json"
            if rebuilt_path.exists():
                file_path = rebuilt_path
            else:
                file_path = config.get_ngrams_path() / f"{lang}.json"

            if file_path.exists():
                with open(file_path, encoding='utf-8') as f:
                    self._models[lang] = json.load(f)
                logger.info(f"Loaded N-gram model for language: {lang} from {file_path}")
            else:
                logger.warning(f"No N-gram model found for language: {lang} at {file_path}, using empty model")
                self._models[lang] = {"bigrams": {}}

        except Exception as e:
            logger.error(f"Failed to load N-gram model for {lang}: {e}")
            self._models[lang] = {"bigrams": {}}

        return self._models[lang]

    def predict_next(
        self,
        user_id: int,
        current_symbols: list[dict],
        limit: int = 5,
        language: str = "en",
        offset: int = 0,
        board_id: int | None = None,
        db: Session | None = None,
        topic: str | None = None,
        topic_word_fetcher: TopicWordFetcher | None = None,
        content_policy=None,
    ) -> list[dict]:
        """
        Predict next symbols.

        Args:
            user_id: User ID
            current_symbols: List of symbols in current utterance
            limit: Max suggestions to return
            language: Language code (e.g., 'en', 'es-ES')
            offset: Pagination offset
            topic_word_fetcher: Optional (language, topic) -> words provider.
                When the catalog cannot cover the topic, generated words are
                surfaced as text-only suggestions so learners are never
                limited by the symbols present in the database.
            content_policy: Optional resolved content-safety policy. When
                given, blocked topics are dropped, blocked topic words are
                never suggested, and pictogram generation for blocked labels
                is skipped (each gate logs a content-safety event).

        Returns:
            List of suggested symbol dicts
        """
        # Real symbol suggestions must get the full requested budget. Punctuation
        # is only a fallback when slots remain; reserving four slots up front
        # made a limit=1 request return punctuation instead of a next symbol.
        #
        # Pagination: generate ``limit + offset`` unique suggestions so a later
        # page can skip the already-seen ones while still returning a full
        # page. The offset is capped so a large page number cannot force an
        # unbounded history/catalog fetch.
        safe_offset = min(offset, 250)
        base_limit = min(limit + safe_offset, 300)

        # Layered content safety: a blocked topic loses its topic tiers (and
        # the custom-topics feature lock drops it entirely) instead of feeding
        # the fetcher or the catalog matcher.
        if content_policy is not None:
            from src.aac_app.services.content_safety import (
                check_text,
                log_event,
            )

            if content_policy.feature_blocked("block_custom_topics"):
                if topic and topic.strip():
                    log_event(
                        user_id=user_id,
                        surface="topic",
                        direction="input",
                        verdict="blocked",
                        detail=f"feature_lock: block_custom_topics; topic: {topic[:120]}",
                        db=db,
                    )
                topic = None
                topic_word_fetcher = None
            elif topic and topic.strip():
                topic_verdict = check_text(content_policy, topic)
                if topic_verdict.blocked:
                    log_event(
                        user_id=user_id,
                        surface="topic",
                        direction="input",
                        verdict="redirected",
                        matched=list(topic_verdict.matched_terms),
                        detail=topic[:300],
                        db=db,
                    )
                    topic = None
                    topic_word_fetcher = None

        context = _PredictionContext(
            user_id=user_id,
            current_symbols=current_symbols,
            language=language,
            offset=safe_offset,
            base_limit=base_limit,
            limit=limit,
            board_id=board_id,
            db=db,
            analytics_service=self.analytics_service,
            load_model=self._load_model,
            topic=topic,
            topic_word_fetcher=topic_word_fetcher,
            content_policy=content_policy,
        )




        # Topic symbols rank first so a study subject actually shapes the
        # Smartbar instead of the same global standard-library words on every
        # topic. When the catalog cannot cover the topic, LLM-generated words
        # (``suggest_topic_words``) fill the gap as text-only suggestions, so
        # learners are never limited by the symbols in the database. Board
        # content comes next (it is the user's chosen scope), then the global
        # fallbacks fill remaining slots. ``suggest_board_library`` is a no-op
        # when no board is scoped, so a single call covers both cases.
        context.suggest_topic()
        context.suggest_topic_words()
        context.suggest_board_library()
        context.suggest_history()
        context.suggest_ngrams()
        context.suggest_popular_symbols()
        context.suggest_standard_library()
        context.suggest_punctuation()

        return context.suggestions[safe_offset : safe_offset + limit]


# Global instance
prediction_service = PredictionService()
