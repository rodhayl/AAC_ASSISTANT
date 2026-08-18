import json
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
from ..services.runtime_translation import normalize_language_code, translate_text
from ..services.symbol_analytics import SymbolAnalytics
from ..services.symbol_catalog import category_is_noun, standard_library_labels

# Punctuation appended after all real suggestions (only when they fit).
PUNCTUATION: tuple[str, ...] = (".", ",", "?", "!")


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

        self.suggestions: list[dict] = []
        self.seen_labels: set[str] = set()

        self.lang = normalize_language_code(language) or "en"
        self.preferred_langs = [self.lang]
        if self.lang != "en":
            self.preferred_langs.append("en")

        self.allowed_symbol_ids: set[int] | None = None
        if board_id is not None:
            self._resolve_allowed_symbol_ids()

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
            self.allowed_symbol_ids = None

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
        if normalize_language_code(symbol_language) == self.lang:
            return label
        return translate_text(label, self.lang) or label

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
        localized_label = self.localize_label(label, symbol_language)
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

    def suggest_fallbacks(self) -> None:
        """Tier 3: most-popular global symbols, interleaving nouns and others."""
        if len(self.suggestions) >= self.base_limit:
            return
        try:
            fallback_suggestions = self.analytics_service.suggest_next_symbol(
                user_id=self.user_id,
                symbols=[],
                limit=max(self.base_limit * 2, 10),  # Request more to filter
                db=self.db,
            )

            # If analytics has no usage data yet, fall back to standard-library
            # symbols but keep the `fallback` source so tier-4 behavior is explicit.
            if not fallback_suggestions:
                resolved = self.resolve_symbols_by_labels(
                    standard_library_labels(self.lang)
                )
                fallback_suggestions = [
                    {
                        "symbol_id": sym.id,
                        "label": sym.label,
                        "category": sym.category,
                        "image_path": sym.image_path,
                    }
                    for sym, _ in resolved[: max(self.base_limit * 2, 10)]
                ]

            # Split fallbacks into nouns and others to mix them.
            noun_candidates = []
            other_candidates = []
            for suggestion in fallback_suggestions:
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
                        source="fallback",
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
                        source="fallback",
                        symbol_language=suggestion.get("language"),
                    )
        except Exception as exc:
            logger.error("Fallback prediction failed: {}", exc)

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
            logger.warning(
                "Board library fallback failed (board_id={}): {}",
                self.board_id,
                exc,
            )

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

    def _load_model(self, language_code: str) -> dict:
        """Load static N-gram model for the given language."""
        lang = normalize_language_code(language_code) or "en"

        if lang in self._models:
            return self._models[lang]

        try:
            # Use frozen-aware path from config
            from src import config
            ngrams_dir = config.get_ngrams_path()
            file_path = ngrams_dir / f"{lang}.json"

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
    ) -> list[dict]:
        """
        Predict next symbols.

        Args:
            user_id: User ID
            current_symbols: List of symbols in current utterance
            limit: Max suggestions to return
            language: Language code (e.g., 'en', 'es-ES')
            offset: Pagination offset

        Returns:
            List of suggested symbol dicts
        """
        reserved_punct = len(PUNCTUATION) if offset == 0 else 0
        base_limit = max(0, limit - reserved_punct)

        context = _PredictionContext(
            user_id=user_id,
            current_symbols=current_symbols,
            language=language,
            offset=offset,
            base_limit=base_limit,
            limit=limit,
            board_id=board_id,
            db=db,
            analytics_service=self.analytics_service,
            load_model=self._load_model,
        )

        context.suggest_history()
        context.suggest_ngrams()
        context.suggest_fallbacks()
        context.suggest_standard_library()
        context.suggest_board_library()
        context.suggest_punctuation()

        return context.suggestions[:limit]


# Global instance
prediction_service = PredictionService()
