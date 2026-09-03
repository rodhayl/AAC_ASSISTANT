"""
Symbol Analytics Service
Tracks and analyzes symbol usage patterns for personalization and insights.
"""

from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import RLock
from weakref import WeakKeyDictionary

from loguru import logger
from sqlalchemy import and_, desc, event, func, or_
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from ..db import get_session, session_scope
from ..models import LearningSession, Symbol, SymbolUsageLog, User

# Upper bound on distinct sequences tracked per get_frequent_sequences call.
# Frequent-sequence output only ever returns ``limit`` rows (default 10), so
# once this budget is exhausted only already-tracked sequences keep counting;
# brand-new distinct sequences are ignored. This keeps memory bounded on very
# long usage histories while preserving exact results below the cap.
MAX_TRACKED_SEQUENCES = 10_000


def _record_sequence(
    sequences: dict,
    seq_key: tuple,
    labels: list[str],
    categories: list[str | None],
    timestamp,
) -> None:
    """Increment an observed utterance sequence under the tracking budget."""
    if seq_key not in sequences:
        if len(sequences) >= MAX_TRACKED_SEQUENCES:
            return
        sequences[seq_key] = {
            "labels": labels,
            "categories": categories,
            "count": 0,
            "last_used": None,
        }
    sequences[seq_key]["count"] += 1
    sequences[seq_key]["last_used"] = timestamp


# Cached per-user prefix->next-label transition indexes.  The index is keyed by
# the owning database engine (weakly) so tests and short-lived engines do not
# leak memory, and usage writes invalidate it so predictions reflect the
# latest history without rescanning the whole table per request.
_history_transition_lock = RLock()
_history_transition_cache: WeakKeyDictionary[
    Engine, dict[int, dict[tuple[str, ...], Counter[str]]]
] = WeakKeyDictionary()


def clear_history_transition_cache() -> None:
    """Invalidate every cached transition index after a symbol usage write."""
    with _history_transition_lock:
        _history_transition_cache.clear()


def _invalidate_history_transitions(*_args) -> None:
    clear_history_transition_cache()


event.listen(SymbolUsageLog, "after_insert", _invalidate_history_transitions)
event.listen(SymbolUsageLog, "after_update", _invalidate_history_transitions)
event.listen(SymbolUsageLog, "after_delete", _invalidate_history_transitions)


class SymbolAnalytics:
    """
    Service for tracking and analyzing AAC symbol usage patterns.
    Provides insights for personalization and usage statistics.
    """

    @staticmethod
    @contextmanager
    def _session_scope(db: Session | None):
        """Keep the historical module-level get_session patch seam."""
        with session_scope(db, session_factory=get_session) as session:
            yield session

    def log_symbol_usage(
        self,
        user_id: int,
        symbols: list[dict],
        session_id: int | None = None,
        semantic_intent: str | None = None,
        context_topic: str | None = None,
        db: Session | None = None,
    ) -> bool:
        """
        Log symbol usage for analytics.

        Args:
            user_id: User who used the symbols
            symbols: List of symbol dicts with id, label, category, position
            session_id: Optional learning session ID
            semantic_intent: Optional detected intent (REQUEST, QUESTION, etc.)
            context_topic: Optional topic context
            db: Optional database session (will create if not provided)

        Returns:
            True if logging successful
        """
        try:
            with self._session_scope(db) as session:
                # SQLite may otherwise treat a first savepoint as the whole
                # transaction. Start an explicit caller-owned transaction so
                # the caller can still commit or roll back the batch.
                if db is not None and (session.new or session.dirty or session.deleted):
                    # Never let optional analytics flush unrelated caller work.
                    # The primary request remains responsible for that work.
                    logger.debug("Skipping analytics while caller session has pending changes")
                    return True
                if db is not None and not session.in_transaction():
                    if session.bind is not None and session.bind.dialect.name == "sqlite":
                        # SQLite needs a raw outer BEGIN for SAVEPOINT rollback
                        # to remain durable until the caller commits/rolls back.
                        session.connection().exec_driver_sql("BEGIN")
                    else:
                        session.begin()
                with session.no_autoflush:
                    utterance_length = len(symbols)
                    symbol_ids = {
                        symbol.get("id")
                        for symbol in symbols
                        if isinstance(symbol.get("id"), int)
                    }
                    valid_symbol_ids = (
                        {
                            symbol_id
                            for (symbol_id,) in session.query(Symbol.id)
                            .filter(Symbol.id.in_(symbol_ids))
                            .all()
                        }
                        if symbol_ids
                        else set()
                    )
                    # Never create orphaned analytics rows when a stale
                    # caller supplies an unknown user. Treat this optional
                    # telemetry as successfully skipped.
                    if session.query(User.id).filter(User.id == user_id).first() is None:
                        logger.debug("Skipping analytics for unknown user {}", user_id)
                        return True

                    valid_session = (
                        session.query(LearningSession.id)
                        .filter(LearningSession.id == session_id)
                        .first()
                        if session_id is not None
                        else None
                    )
                    safe_session_id = session_id if session_id is None or valid_session else None

                    for idx, symbol in enumerate(symbols):
                        symbol_id = symbol.get("id")
                        usage_log = SymbolUsageLog(
                            user_id=user_id,
                            session_id=safe_session_id,
                            symbol_id=(
                                symbol_id if symbol_id in valid_symbol_ids else None
                            ),
                            symbol_label=symbol.get("label", ""),
                            symbol_category=symbol.get("category"),
                            position_in_utterance=idx,
                            utterance_length=utterance_length,
                            semantic_intent=semantic_intent,
                            context_topic=context_topic,
                        )
                        try:
                            # Analytics is best-effort. A stale FK must not
                            # poison the caller's main learning transaction.
                            with session.begin_nested():
                                session.add(usage_log)
                                session.flush()
                        except IntegrityError:
                            logger.warning(
                                "Skipping invalid symbol analytics row for user {}",
                                user_id,
                            )

                # The shared scope commits only sessions it created. A caller
                # supplied request session remains responsible for its commit.
            logger.debug(f"Logged {len(symbols)} symbols for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to log symbol usage: {e}")
            return False

    def get_frequent_sequences(
        self,
        user_id: int,
        limit: int = 10,
        min_occurrences: int = 2,
        db: Session | None = None,
    ) -> list[dict]:
        """
        Find user's most common symbol sequences.

        Args:
            user_id: User ID to analyze
            limit: Maximum sequences to return
            min_occurrences: Minimum times sequence must appear

        Returns:
            List of dicts with sequence info
        """
        with self._session_scope(db) as db:
            # Get all usage logs for user, ordered by session and position
            logs_query = (
                db.query(SymbolUsageLog)
                .filter(SymbolUsageLog.user_id == user_id)
                .order_by(
                    SymbolUsageLog.session_id,
                    SymbolUsageLog.timestamp,
                    SymbolUsageLog.position_in_utterance,
                )
            )

            # Stream the ordered history in batches. This preserves the exact
            # sequence semantics while avoiding a second in-memory copy of a
            # user's entire usage history.
            logs = logs_query.yield_per(1000)

            # Build sequences from consecutive utterances
            sequences = {}
            current_sequence = []
            current_session = None
            current_timestamp = None
            last_position: int | None = None

            for log in logs:
                # A repeated/decreasing position starts a new utterance even
                # when clients reuse a session ID for several sentences.
                position_reset = (
                    last_position is not None
                    and log.position_in_utterance is not None
                    and log.position_in_utterance <= last_position
                )
                time_gap = (
                    current_timestamp is not None
                    and log.timestamp is not None
                    and (log.timestamp - current_timestamp).total_seconds() > 300
                )
                if current_session != log.session_id or position_reset or time_gap:
                    if len(current_sequence) >= 2:
                        _record_sequence(
                            sequences,
                            tuple(s["label"] for s in current_sequence),
                            [s["label"] for s in current_sequence],
                            [s["category"] for s in current_sequence],
                            current_timestamp,
                        )

                    current_sequence = []

                current_sequence.append(
                    {
                        "label": log.symbol_label,
                        "category": log.symbol_category,
                        "position": log.position_in_utterance,
                    }
                )
                current_session = log.session_id
                current_timestamp = log.timestamp
                last_position = log.position_in_utterance

            # Add final sequence
            if len(current_sequence) >= 2:
                _record_sequence(
                    sequences,
                    tuple(s["label"] for s in current_sequence),
                    [s["label"] for s in current_sequence],
                    [s["category"] for s in current_sequence],
                    current_timestamp,
                )

            # Filter by minimum occurrences and sort by frequency
            frequent = [
                {**seq_data, "sequence": " → ".join(seq_data["labels"])}
                for seq_key, seq_data in sequences.items()
                if seq_data["count"] >= min_occurrences
            ]

            frequent.sort(key=lambda x: x["count"], reverse=True)
            return frequent[:limit]

    def get_category_preferences(
        self, user_id: int, db: Session | None = None
    ) -> dict:
        """
        Analyze which symbol categories user uses most.

        Args:
            user_id: User ID to analyze

        Returns:
            Dict with category usage statistics
        """
        with self._session_scope(db) as db:
            # Count usage by category
            category_counts = (
                db.query(
                    SymbolUsageLog.symbol_category,
                    func.count(SymbolUsageLog.id).label("count"),
                )
                .filter(
                    SymbolUsageLog.user_id == user_id,
                    SymbolUsageLog.symbol_category.isnot(None),
                )
                .group_by(SymbolUsageLog.symbol_category)
                .order_by(desc("count"))
                .all()
            )

            total_symbols = sum(count for _, count in category_counts)

            categories = {}
            for category, count in category_counts:
                categories[category] = {
                    "count": count,
                    "percentage": (
                        round((count / total_symbols * 100), 1)
                        if total_symbols > 0
                        else 0
                    ),
                }

            return {
                "categories": categories,
                "total_symbols_used": total_symbols,
                "unique_categories": len(categories),
            }

    def get_usage_stats(
        self, user_id: int, days: int = 30, db: Session | None = None
    ) -> dict:
        """
        Get overall usage statistics for user.

        Args:
            user_id: User ID to analyze
            days: Number of days to look back

        Returns:
            Dict with usage statistics
        """
        with self._session_scope(db) as db:
            # Usage-log timestamps use a legacy naive DateTime column whose
            # values are stored as UTC; keep the comparison representation
            # naive for SQLite and other supported databases.
            cutoff_date = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

            # Total symbols used
            total_count = (
                db.query(func.count(SymbolUsageLog.id))
                .filter(
                    SymbolUsageLog.user_id == user_id,
                    SymbolUsageLog.timestamp >= cutoff_date,
                )
                .scalar()
            )

            # Unique symbols
            unique_count = (
                db.query(func.count(func.distinct(SymbolUsageLog.symbol_id)))
                .filter(
                    SymbolUsageLog.user_id == user_id,
                    SymbolUsageLog.timestamp >= cutoff_date,
                    SymbolUsageLog.symbol_id.isnot(None),
                )
                .scalar()
            )

            # Most used symbols
            most_used = (
                db.query(
                    SymbolUsageLog.symbol_label,
                    SymbolUsageLog.symbol_category,
                    func.count(SymbolUsageLog.id).label("count"),
                )
                .filter(
                    SymbolUsageLog.user_id == user_id,
                    SymbolUsageLog.timestamp >= cutoff_date,
                )
                .group_by(SymbolUsageLog.symbol_label, SymbolUsageLog.symbol_category)
                .order_by(desc("count"))
                .limit(10)
                .all()
            )

            # Intent distribution
            intent_counts = (
                db.query(
                    SymbolUsageLog.semantic_intent,
                    func.count(SymbolUsageLog.id).label(
                        "utterance_count"
                    ),
                )
                .filter(
                    SymbolUsageLog.user_id == user_id,
                    SymbolUsageLog.timestamp >= cutoff_date,
                    SymbolUsageLog.semantic_intent.isnot(None),
                    SymbolUsageLog.position_in_utterance
                    == 0,  # Count each utterance once
                )
                .group_by(SymbolUsageLog.semantic_intent)
                .all()
            )

            intents = {intent: count for intent, count in intent_counts if intent}

            # Average utterance length
            avg_length = (
                db.query(func.avg(SymbolUsageLog.utterance_length))
                .filter(
                    SymbolUsageLog.user_id == user_id,
                    SymbolUsageLog.timestamp >= cutoff_date,
                    SymbolUsageLog.position_in_utterance
                    == 0,  # Count each utterance once
                )
                .scalar()
                or 0
            )

            return {
                "period_days": days,
                "total_symbols_used": total_count or 0,
                "unique_symbols": unique_count or 0,
                "average_utterance_length": round(avg_length, 1),
                "most_used_symbols": [
                    {"label": label, "category": category, "count": count}
                    for label, category, count in most_used
                ],
                "intent_distribution": intents,
            }

    def get_history_transitions(
        self,
        user_id: int,
        db: Session | None = None,
    ) -> dict[tuple[str, ...], Counter[str]]:
        """Return observed ``prefix -> next label`` counts for one user.

        The index is built once per user and cached per database engine; symbol
        usage writes invalidate it so predictions observe the latest history
        without rescanning the full table on every request.
        """
        with self._session_scope(db) as session:
            engine = session.get_bind()
            with _history_transition_lock:
                per_user = _history_transition_cache.get(engine)
                if per_user is not None:
                    cached = per_user.get(user_id)
                    if cached is not None:
                        return cached

            index = self._build_history_transitions(session, user_id)

            with _history_transition_lock:
                _history_transition_cache.setdefault(engine, {}).setdefault(
                    user_id, index
                )
            return index

    def _build_history_transitions(
        self, session: Session, user_id: int
    ) -> dict[tuple[str, ...], Counter[str]]:
        """Stream a user's ordered history and index prefix-to-next transitions."""
        logs_query = (
            session.query(SymbolUsageLog)
            .filter(SymbolUsageLog.user_id == user_id)
            .order_by(
                SymbolUsageLog.session_id,
                SymbolUsageLog.timestamp,
                SymbolUsageLog.position_in_utterance,
            )
        )
        logs = logs_query.yield_per(1000)

        transitions: dict[tuple[str, ...], Counter[str]] = {}
        current_sequence: list[str] = []
        current_session = None
        current_timestamp: datetime | None = None
        last_position: int | None = None

        def record_sequence(sequence: list[str]) -> None:
            for i in range(len(sequence) - 1):
                prefix = tuple(sequence[: i + 1])
                next_label = sequence[i + 1]
                if not next_label or not all(prefix):
                    continue
                transitions.setdefault(prefix, Counter())[next_label] += 1

        for log in logs:
            # Start a new utterance on a session, a position reset, or a
            # >5-minute time boundary. Position resets matter because a client
            # can keep one learning session open across multiple utterances.
            position_reset = (
                last_position is not None
                and log.position_in_utterance is not None
                and log.position_in_utterance <= last_position
            )
            time_gap = (
                current_timestamp is not None
                and log.timestamp is not None
                and (log.timestamp - current_timestamp).total_seconds() > 300
            )
            if current_session != log.session_id or position_reset or time_gap:
                if len(current_sequence) >= 2:
                    record_sequence(current_sequence)
                current_sequence = []

            current_sequence.append((log.symbol_label or "").strip())
            current_session = log.session_id
            current_timestamp = log.timestamp
            last_position = log.position_in_utterance

        if len(current_sequence) >= 2:
            record_sequence(current_sequence)

        return transitions

    def _sequence_suggestions(
        self,
        session: Session,
        user_id: int,
        labels: list[str],
        limit: int,
    ) -> list[dict] | None:
        """Resolve next symbols from the longest matching utterance suffix."""
        transitions = self.get_history_transitions(user_id, db=session)
        for start in range(len(labels)):
            counts = transitions.get(tuple(labels[start:]))
            if not counts:
                continue

            total = sum(counts.values())
            ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            suggestions: list[dict] = []
            for next_label, count in ordered:
                symbol = (
                    session.query(Symbol)
                    .filter(func.lower(Symbol.label) == next_label.casefold())
                    .order_by(Symbol.id)
                    .first()
                )
                if symbol is None:
                    continue
                suggestions.append(
                    {
                        "symbol_id": symbol.id,
                        "label": next_label,
                        "category": symbol.category,
                        "image_path": symbol.image_path,
                        "language": symbol.language,
                        "confidence": round(count / total, 2) if total else 0.5,
                    }
                )
                if len(suggestions) >= limit:
                    break
            if suggestions:
                return suggestions
        return None

    def suggest_next_symbol(
        self,
        user_id: int,
        symbols: list[dict],
        limit: int = 5,
        db: Session | None = None,
    ) -> list[dict]:
        """
        Predict next symbol based on usage history.

        Args:
            user_id: User ID
            symbols: Symbols in current utterance
            limit: Max suggestions to return

        Returns:
            List of suggested symbols with confidence scores
        """
        if not symbols:
            # Return most frequently used symbols
            with self._session_scope(db) as db:
                # Read the label from the live Symbol row, not the denormalized
                # usage-log label: the log keeps whatever label the symbol had
                # when it was used, so a renamed symbol (or a stale test
                # label) would otherwise surface outdated text with the
                # current image.
                most_used = (
                    db.query(
                        SymbolUsageLog.symbol_id,
                        Symbol.label,
                        Symbol.category,
                        Symbol.image_path,
                        Symbol.language,
                        func.count(SymbolUsageLog.id).label("count"),
                    )
                    .join(Symbol, Symbol.id == SymbolUsageLog.symbol_id)
                    .filter(
                        SymbolUsageLog.user_id == user_id,
                        SymbolUsageLog.symbol_id.isnot(None),
                    )
                    .group_by(
                        SymbolUsageLog.symbol_id,
                        Symbol.label,
                        Symbol.category,
                        Symbol.image_path,
                        Symbol.language,
                    )
                    .order_by(desc("count"))
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "symbol_id": symbol_id,
                        "label": label,
                        "category": category,
                        "image_path": image_path,
                        "language": language_code,
                        "confidence": 0.5,  # Default confidence for frequency-based
                    }
                    for symbol_id, label, category, image_path, language_code, _ in most_used
                ]

        # Find patterns where current sequence appears
        current_labels = [s.get("label") for s in symbols]

        with self._session_scope(db) as db:
            # Prefer the longest matching suffix of the current utterance so
            # multi-word predictions ("I want") rank next words seen after the
            # full sequence before falling back to the last word alone.
            if len(current_labels) >= 2:
                sequence_hits = self._sequence_suggestions(
                    db, user_id, current_labels, limit
                )
                if sequence_hits:
                    return sequence_hits

            # Find transitions in one self-join instead of querying once per
            # matching log. The explicit NULL branch preserves the historical
            # Python behavior where two missing session IDs match each other.
            last_label = current_labels[-1]
            current_log = aliased(SymbolUsageLog)
            next_log = aliased(SymbolUsageLog)
            candidate_log = aliased(SymbolUsageLog)
            candidate_same_session = or_(
                current_log.session_id == candidate_log.session_id,
                and_(
                    current_log.session_id.is_(None),
                    candidate_log.session_id.is_(None),
                ),
            )
            first_next_id = (
                db.query(func.min(candidate_log.id))
                .filter(
                    candidate_log.user_id == current_log.user_id,
                    candidate_same_session,
                    candidate_log.position_in_utterance
                    == current_log.position_in_utterance + 1,
                )
                .correlate(current_log)
                .scalar_subquery()
            )
            # Read the label from the live Symbol row, not the denormalized
            # usage-log label: the log keeps whatever label the symbol had
            # when it was used, so a renamed symbol (or a stale test label)
            # would otherwise surface outdated text with the current image.
            # The Symbol join is 1:1 on the PK, so counts are unaffected.
            transition_counts = (
                db.query(
                    next_log.symbol_id,
                    Symbol.label,
                    Symbol.category,
                    func.count(current_log.id).label("count"),
                    func.min(current_log.id).label("first_current_id"),
                )
                .select_from(current_log)
                .join(next_log, next_log.id == first_next_id)
                .join(Symbol, Symbol.id == next_log.symbol_id)
                .filter(
                    current_log.user_id == user_id,
                    current_log.symbol_label == last_label,
                    next_log.symbol_label.isnot(None),
                    next_log.symbol_label != "",
                )
                .group_by(
                    next_log.symbol_id,
                    Symbol.label,
                    Symbol.category,
                )
                # The old Python accumulator was stable for ties because it
                # encountered current logs in database order. Use the first
                # current-log ID as an explicit deterministic tie-breaker.
                .order_by(desc("count"), "first_current_id")
                .limit(limit)
                .all()
            )

            # SQL performs both first-next selection and counting, so Python
            # only handles the small result set needed for response shaping.
            sorted_symbols = [
                ((symbol_id, label, category), count)
                for symbol_id, label, category, count, _ in transition_counts
            ]
            total_count = sum(count for _, count in sorted_symbols)

            # Fetch image paths for these symbols
            symbol_ids = [sid for (sid, _, _), _ in sorted_symbols]
            symbol_details = {}
            if symbol_ids:
                symbols_db = (
                    db.query(Symbol.id, Symbol.image_path, Symbol.language)
                    .filter(Symbol.id.in_(symbol_ids))
                    .all()
                )
                symbol_details = {
                    s.id: {"image_path": s.image_path, "language": s.language}
                    for s in symbols_db
                }

            return [
                {
                    "symbol_id": symbol_id,
                    "label": label,
                    "category": category,
                    "image_path": symbol_details.get(symbol_id, {}).get("image_path"),
                    "language": symbol_details.get(symbol_id, {}).get("language"),
                    "confidence": (
                        round(count / total_count, 2) if total_count > 0 else 0.5
                    ),
                }
                for (symbol_id, label, category), count in sorted_symbols
            ]
