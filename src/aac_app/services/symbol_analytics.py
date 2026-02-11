"""
Symbol Analytics Service
Tracks and analyzes symbol usage patterns for personalization and insights.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..models.database import Symbol, SymbolUsageLog, get_session


class SymbolAnalytics:
    """
    Service for tracking and analyzing AAC symbol usage patterns.
    Provides insights for personalization and usage statistics.
    """

    def log_symbol_usage(
        self,
        user_id: int,
        symbols: List[Dict],
        session_id: Optional[int] = None,
        semantic_intent: Optional[str] = None,
        context_topic: Optional[str] = None,
        db: Optional[Session] = None,
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
            close_session = False
            if db is None:
                # get_session() is a context manager, we need to enter it
                ctx = get_session()
                db = ctx.__enter__()
                close_session = True
                self._ctx = ctx  # Store to exit later

            utterance_length = len(symbols)

            for idx, symbol in enumerate(symbols):
                usage_log = SymbolUsageLog(
                    user_id=user_id,
                    session_id=session_id,
                    symbol_id=symbol.get("id"),
                    symbol_label=symbol.get("label", ""),
                    symbol_category=symbol.get("category"),
                    position_in_utterance=idx,
                    utterance_length=utterance_length,
                    semantic_intent=semantic_intent,
                    context_topic=context_topic,
                )
                db.add(usage_log)

            db.commit()
            logger.debug(f"Logged {len(symbols)} symbols for user {user_id}")

            if close_session and hasattr(self, '_ctx'):
                self._ctx.__exit__(None, None, None)

            return True

        except Exception as e:
            logger.error(f"Failed to log symbol usage: {e}")
            if db is not None:
                db.rollback()
            if db and close_session and hasattr(self, '_ctx'):
                self._ctx.__exit__(type(e), e, e.__traceback__)
            return False

    def get_frequent_sequences(
        self, user_id: int, limit: int = 10, min_occurrences: int = 2
    ) -> List[Dict]:
        """
        Find user's most common symbol sequences.

        Args:
            user_id: User ID to analyze
            limit: Maximum sequences to return
            min_occurrences: Minimum times sequence must appear

        Returns:
            List of dicts with sequence info
        """
        with get_session() as db:
            # Get all usage logs for user, ordered by session and position
            logs = (
                db.query(SymbolUsageLog)
                .filter(SymbolUsageLog.user_id == user_id)
                .order_by(
                    SymbolUsageLog.session_id,
                    SymbolUsageLog.timestamp,
                    SymbolUsageLog.position_in_utterance,
                )
                .all()
            )

            # Build sequences from consecutive utterances
            sequences = {}
            current_sequence = []
            current_session = None
            current_timestamp = None

            for log in logs:
                # Start new sequence if different session or time gap > 5 minutes
                if current_session != log.session_id or (
                    current_timestamp
                    and (log.timestamp - current_timestamp).seconds > 300
                ):
                    if len(current_sequence) >= 2:
                        seq_key = tuple([s["label"] for s in current_sequence])
                        if seq_key not in sequences:
                            sequences[seq_key] = {
                                "labels": [s["label"] for s in current_sequence],
                                "categories": [s["category"] for s in current_sequence],
                                "count": 0,
                                "last_used": None,
                            }
                        sequences[seq_key]["count"] += 1
                        sequences[seq_key]["last_used"] = current_timestamp

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

            # Add final sequence
            if len(current_sequence) >= 2:
                seq_key = tuple([s["label"] for s in current_sequence])
                if seq_key not in sequences:
                    sequences[seq_key] = {
                        "labels": [s["label"] for s in current_sequence],
                        "categories": [s["category"] for s in current_sequence],
                        "count": 0,
                        "last_used": None,
                    }
                sequences[seq_key]["count"] += 1
                sequences[seq_key]["last_used"] = current_timestamp

            # Filter by minimum occurrences and sort by frequency
            frequent = [
                {**seq_data, "sequence": " → ".join(seq_data["labels"])}
                for seq_key, seq_data in sequences.items()
                if seq_data["count"] >= min_occurrences
            ]

            frequent.sort(key=lambda x: x["count"], reverse=True)
            return frequent[:limit]

    def get_category_preferences(self, user_id: int) -> Dict:
        """
        Analyze which symbol categories user uses most.

        Args:
            user_id: User ID to analyze

        Returns:
            Dict with category usage statistics
        """
        with get_session() as db:
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

    def get_usage_stats(self, user_id: int, days: int = 30) -> Dict:
        """
        Get overall usage statistics for user.

        Args:
            user_id: User ID to analyze
            days: Number of days to look back

        Returns:
            Dict with usage statistics
        """
        with get_session() as db:
            cutoff_date = datetime.now() - timedelta(days=days)

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
                    func.count(func.distinct(SymbolUsageLog.session_id)).label(
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

    def suggest_next_symbol(
        self, user_id: int, symbols: List[Dict], limit: int = 5
    ) -> List[Dict]:
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
            with get_session() as db:
                most_used = (
                    db.query(
                        SymbolUsageLog.symbol_id,
                        SymbolUsageLog.symbol_label,
                        SymbolUsageLog.symbol_category,
                        Symbol.image_path,
                        func.count(SymbolUsageLog.id).label("count"),
                    )
                    .join(Symbol, Symbol.id == SymbolUsageLog.symbol_id)
                    .filter(
                        SymbolUsageLog.user_id == user_id,
                        SymbolUsageLog.symbol_id.isnot(None),
                    )
                    .group_by(
                        SymbolUsageLog.symbol_id,
                        SymbolUsageLog.symbol_label,
                        SymbolUsageLog.symbol_category,
                        Symbol.image_path,
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
                        "confidence": 0.5,  # Default confidence for frequency-based
                    }
                    for symbol_id, label, category, image_path, _ in most_used
                ]

        # Find patterns where current sequence appears
        current_labels = [s.get("label") for s in symbols]

        with get_session() as db:
            # Look for usage logs that match the current sequence
            # This is a simplified implementation - could be enhanced with n-grams
            last_label = current_labels[-1]

            # Find all logs where the last label was used
            matching_logs = (
                db.query(SymbolUsageLog)
                .filter(
                    SymbolUsageLog.user_id == user_id,
                    SymbolUsageLog.symbol_label == last_label,
                )
                .all()
            )

            # For each matching log, find the next symbol in the same utterance
            next_symbol_counts = {}
            for log in matching_logs:
                # Query for the next symbol (same session_id, position + 1)
                next_log = (
                    db.query(SymbolUsageLog)
                    .filter(
                        SymbolUsageLog.user_id == user_id,
                        SymbolUsageLog.session_id == log.session_id,
                        SymbolUsageLog.position_in_utterance
                        == log.position_in_utterance + 1,
                    )
                    .first()
                )

                if next_log and next_log.symbol_label:
                    key = (
                        next_log.symbol_id,
                        next_log.symbol_label,
                        next_log.symbol_category,
                    )
                    next_symbol_counts[key] = next_symbol_counts.get(key, 0) + 1

            # Sort by count and take top N
            sorted_symbols = sorted(
                next_symbol_counts.items(), key=lambda x: x[1], reverse=True
            )[:limit]
            total_count = sum(count for _, count in sorted_symbols)

            # Fetch image paths for these symbols
            symbol_ids = [sid for (sid, _, _), _ in sorted_symbols]
            images = {}
            if symbol_ids:
                symbols_db = (
                    db.query(Symbol.id, Symbol.image_path)
                    .filter(Symbol.id.in_(symbol_ids))
                    .all()
                )
                images = {s.id: s.image_path for s in symbols_db}

            return [
                {
                    "symbol_id": symbol_id,
                    "label": label,
                    "category": category,
                    "image_path": images.get(symbol_id),
                    "confidence": (
                        round(count / total_count, 2) if total_count > 0 else 0.5
                    ),
                }
                for (symbol_id, label, category), count in sorted_symbols
            ]
