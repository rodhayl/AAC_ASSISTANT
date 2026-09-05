"""Focused regression tests for symbol analytics suggestions."""

from datetime import datetime, timedelta

from sqlalchemy import event

from src.aac_app.models import LearningSession, Symbol, SymbolUsageLog
from src.aac_app.services import symbol_analytics as symbol_analytics_module
from src.aac_app.services.symbol_analytics import SymbolAnalytics


def _add_log(
    session,
    *,
    user_id: int,
    label: str,
    symbol_id: int | None,
    position: int,
    session_id: int | None = None,
    timestamp: datetime | None = None,
) -> None:
    session.add(
        SymbolUsageLog(
            user_id=user_id,
            session_id=session_id,
            symbol_id=symbol_id,
            symbol_label=label,
            symbol_category="test",
            position_in_utterance=position,
            utterance_length=2,
            timestamp=timestamp,
        )
    )


def test_frequent_sequences_bounds_tracked_distinct_sequences(
    test_db_session, regular_user, monkeypatch
):
    """Frequent-sequence memory stays bounded once the tracking budget is used."""
    monkeypatch.setattr(symbol_analytics_module, "MAX_TRACKED_SEQUENCES", 2)

    sessions = [
        LearningSession(user_id=regular_user.id, topic_name=f"seq{i}")
        for i in range(3)
    ]
    test_db_session.add_all(sessions)
    test_db_session.flush()
    for session in sessions:
        _add_log(
            test_db_session,
            user_id=regular_user.id,
            label="I",
            symbol_id=None,
            position=0,
            session_id=session.id,
        )
        _add_log(
            test_db_session,
            user_id=regular_user.id,
            label=session.topic_name,
            symbol_id=None,
            position=1,
            session_id=session.id,
        )
    test_db_session.commit()

    sequences = SymbolAnalytics().get_frequent_sequences(
        regular_user.id,
        limit=10,
        min_occurrences=1,
        db=test_db_session,
    )

    # The two earliest distinct sequences are tracked exactly; the third is
    # ignored once the budget is exhausted.
    assert {item["sequence"] for item in sequences} == {"I → seq0", "I → seq1"}


def test_frequent_sequences_preserves_session_and_time_boundaries(
    test_db_session, regular_user
):
    """Streaming history keeps repeated utterance counts and time boundaries."""
    session = LearningSession(user_id=regular_user.id, topic_name="sequence")
    test_db_session.add(session)
    test_db_session.flush()
    start = datetime(2024, 1, 1, 12, 0, 0)

    for offset in (0, 1):
        base = start + timedelta(minutes=offset * 10)
        _add_log(
            test_db_session,
            user_id=regular_user.id,
            label="I",
            symbol_id=None,
            position=0,
            session_id=session.id,
            timestamp=base,
        )
        _add_log(
            test_db_session,
            user_id=regular_user.id,
            label="want",
            symbol_id=None,
            position=1,
            session_id=session.id,
            timestamp=base + timedelta(seconds=1),
        )
    test_db_session.commit()

    sequences = SymbolAnalytics().get_frequent_sequences(
        regular_user.id,
        limit=5,
        min_occurrences=2,
        db=test_db_session,
    )

    assert sequences[0]["sequence"] == "I → want"
    assert sequences[0]["count"] == 2


def test_frequent_sequences_breaks_after_multi_day_gap(
    test_db_session, regular_user
):
    """A gap of more than five minutes must not be reduced modulo one day."""
    session = LearningSession(user_id=regular_user.id, topic_name="long-gap")
    test_db_session.add(session)
    test_db_session.flush()
    start = datetime(2024, 1, 1, 12, 0, 0)
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="I",
        symbol_id=None,
        position=0,
        session_id=session.id,
        timestamp=start,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="want",
        symbol_id=None,
        position=1,
        session_id=session.id,
        timestamp=start + timedelta(seconds=1),
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="cookie",
        symbol_id=None,
        position=2,
        session_id=session.id,
        timestamp=start + timedelta(days=1),
    )
    test_db_session.commit()

    sequences = SymbolAnalytics().get_frequent_sequences(
        regular_user.id,
        limit=5,
        min_occurrences=1,
        db=test_db_session,
    )

    assert [item["sequence"] for item in sequences] == ["I → want"]


def test_suggest_next_symbol_handles_null_sessions_and_duplicate_next_rows(
    test_db_session, regular_user
):
    """One current log counts only its first matching next log, including NULL sessions."""
    want = Symbol(label="want", category="verb", language="en", image_path="want.png")
    cookie = Symbol(label="cookie", category="noun", language="en", image_path="cookie.png")
    test_db_session.add_all([want, cookie])
    test_db_session.flush()

    # With session_id=None, the old Python implementation treated NULL as a
    # matching session. Duplicate next rows must still behave like .first().
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="I",
        symbol_id=None,
        position=0,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="want",
        symbol_id=want.id,
        position=1,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="want",
        symbol_id=want.id,
        position=1,
    )
    test_db_session.commit()

    suggestions = SymbolAnalytics().suggest_next_symbol(
        regular_user.id,
        [{"label": "I"}],
        db=test_db_session,
    )

    # Metadata (category, image, language) is read from the live Symbol row,
    # not the denormalized usage-log snapshot.
    assert suggestions == [
        {
            "symbol_id": want.id,
            "label": "want",
            "category": "verb",
            "image_path": "want.png",
            "language": "en",
            "confidence": 1.0,
        }
    ]


def test_suggest_next_symbol_uses_constant_query_count_and_stable_ties(
    test_db_session, regular_user
):
    """Transition lookup stays bounded at two SQL statements and preserves tie order."""
    want = Symbol(label="want", category="verb", language="en", image_path="want.png")
    cookie = Symbol(label="cookie", category="noun", language="en", image_path="cookie.png")
    test_db_session.add_all([want, cookie])
    test_db_session.flush()

    session_one = LearningSession(user_id=regular_user.id, topic_name="test")
    session_two = LearningSession(user_id=regular_user.id, topic_name="test")
    other_session = LearningSession(user_id=regular_user.id, topic_name="other")
    unrelated_session = LearningSession(user_id=regular_user.id, topic_name="unrelated")
    test_db_session.add_all([session_one, session_two, other_session, unrelated_session])
    test_db_session.flush()

    # Each valid transition has the same count. The current log insertion
    # order is the tie order retained by the Python accumulator. The extra
    # rows below prove that user, session, and consecutive-position filters
    # remain part of the optimized query.
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="I",
        symbol_id=None,
        position=0,
        session_id=session_one.id,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="want",
        symbol_id=want.id,
        position=1,
        session_id=session_one.id,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="I",
        symbol_id=None,
        position=0,
        session_id=session_two.id,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="cookie",
        symbol_id=cookie.id,
        position=1,
        session_id=session_two.id,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="I",
        symbol_id=None,
        position=0,
        session_id=other_session.id,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="ignored-session",
        symbol_id=want.id,
        position=1,
        session_id=unrelated_session.id,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="ignored-position",
        symbol_id=cookie.id,
        position=2,
        session_id=session_one.id,
    )
    test_db_session.commit()

    user_id = regular_user.id
    statement_count = 0

    def count_statements(*_args):
        nonlocal statement_count
        statement_count += 1

    event.listen(test_db_session.bind, "before_cursor_execute", count_statements)
    try:
        suggestions = SymbolAnalytics().suggest_next_symbol(
            user_id,
            [{"label": "I"}],
            db=test_db_session,
        )
    finally:
        event.remove(test_db_session.bind, "before_cursor_execute", count_statements)

    assert statement_count == 2
    assert [item["label"] for item in suggestions] == ["want", "cookie"]
    assert [item["confidence"] for item in suggestions] == [0.5, 0.5]


def test_suggest_next_symbol_excludes_other_users(
    test_db_session, regular_user
):
    """Suggestions never use transitions belonging to another user."""
    from src.aac_app.models import User

    other_user = User(
        username="analytics-other",
        password_hash="test",
        display_name="Other User",
        user_type="standard",
        is_active=True,
    )
    symbol = Symbol(label="mine", category="test", language="en")
    other_symbol = Symbol(label="other", category="test", language="en")
    test_db_session.add_all([other_user, symbol, other_symbol])
    test_db_session.flush()
    _add_log(
        test_db_session,
        user_id=other_user.id,
        label="I",
        symbol_id=None,
        position=0,
    )
    _add_log(
        test_db_session,
        user_id=other_user.id,
        label="other",
        symbol_id=other_symbol.id,
        position=1,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="I",
        symbol_id=None,
        position=0,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="mine",
        symbol_id=symbol.id,
        position=1,
    )
    test_db_session.commit()

    suggestions = SymbolAnalytics().suggest_next_symbol(
        regular_user.id,
        [{"label": "I"}],
        db=test_db_session,
    )

    assert [item["label"] for item in suggestions] == ["mine"]


def test_suggest_next_symbol_prefers_longest_sequence_match(
    test_db_session, regular_user
):
    """Multi-word input ranks next words seen after the full sequence first."""
    want = Symbol(label="want", category="verb", language="en")
    cookie = Symbol(label="cookie", category="noun", language="en")
    milk = Symbol(label="milk", category="noun", language="en")
    test_db_session.add_all([want, cookie, milk])
    test_db_session.flush()

    session_one = LearningSession(user_id=regular_user.id, topic_name="seq1")
    session_two = LearningSession(user_id=regular_user.id, topic_name="seq2")
    test_db_session.add_all([session_one, session_two])
    test_db_session.flush()

    # "I want cookie"
    _add_log(
        test_db_session, user_id=regular_user.id, label="I", symbol_id=None,
        position=0, session_id=session_one.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="want",
        symbol_id=want.id, position=1, session_id=session_one.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="cookie",
        symbol_id=cookie.id, position=2, session_id=session_one.id,
    )
    # "want milk"
    _add_log(
        test_db_session, user_id=regular_user.id, label="want",
        symbol_id=want.id, position=0, session_id=session_two.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="milk",
        symbol_id=milk.id, position=1, session_id=session_two.id,
    )
    test_db_session.commit()

    # The full "I want" prefix only ever precedes "cookie".
    suggestions = SymbolAnalytics().suggest_next_symbol(
        regular_user.id,
        [{"label": "I"}, {"label": "want"}],
        db=test_db_session,
    )
    assert [item["label"] for item in suggestions] == ["cookie"]

    # The single-word fallback still surfaces both transitions for "want".
    unigram = SymbolAnalytics().suggest_next_symbol(
        regular_user.id,
        [{"label": "want"}],
        db=test_db_session,
    )
    assert {item["label"] for item in unigram} == {"cookie", "milk"}


def test_suggest_next_symbol_falls_back_to_shorter_suffix(
    test_db_session, regular_user
):
    """A missing full-sequence match falls back to the longest matching suffix."""
    want = Symbol(label="want", category="verb", language="en")
    milk = Symbol(label="milk", category="noun", language="en")
    test_db_session.add_all([want, milk])
    test_db_session.flush()

    session = LearningSession(user_id=regular_user.id, topic_name="seq")
    test_db_session.add(session)
    test_db_session.flush()

    _add_log(
        test_db_session, user_id=regular_user.id, label="want",
        symbol_id=want.id, position=0, session_id=session.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="milk",
        symbol_id=milk.id, position=1, session_id=session.id,
    )
    test_db_session.commit()

    suggestions = SymbolAnalytics().suggest_next_symbol(
        regular_user.id,
        [{"label": "I"}, {"label": "want"}],
        db=test_db_session,
    )
    assert [item["label"] for item in suggestions] == ["milk"]



def test_usage_stats_counts_each_utterance_even_without_session_id(
    test_db_session, regular_user
):
    """Intent and length stats count every position-zero utterance record."""
    base = datetime.now() - timedelta(minutes=1)
    shared_session = LearningSession(user_id=regular_user.id, topic_name="shared")
    test_db_session.add(shared_session)
    test_db_session.flush()

    utterances = ((None, 0), (None, 1), (shared_session.id, 2), (shared_session.id, 3))
    for session_id, index in utterances:
        timestamp = base + timedelta(seconds=index)
        _add_log(
            test_db_session,
            user_id=regular_user.id,
            label="I",
            symbol_id=None,
            position=0,
            session_id=session_id,
            timestamp=timestamp,
        )
        _add_log(
            test_db_session,
            user_id=regular_user.id,
            label="want",
            symbol_id=None,
            position=1,
            session_id=session_id,
            timestamp=timestamp + timedelta(milliseconds=1),
        )
    # Mark each utterance start after insertion; selecting by position avoids
    # relying on SQLite's datetime string precision in a per-row range query.
    test_db_session.flush()
    for log in test_db_session.query(SymbolUsageLog).filter(
        SymbolUsageLog.position_in_utterance == 0
    ):
        log.semantic_intent = "REQUEST"
        log.utterance_length = 2

    test_db_session.commit()

    stats = SymbolAnalytics().get_usage_stats(
        regular_user.id, days=1, db=test_db_session
    )

    assert stats["intent_distribution"] == {"REQUEST": 4}
    assert stats["average_utterance_length"] == 2.0


def test_history_transitions_cache_reflects_new_usage(
    test_db_session, regular_user
):
    """The cached transition index is invalidated by symbol usage writes."""
    cookie = Symbol(label="cookie", category="noun", language="en")
    test_db_session.add(cookie)
    test_db_session.flush()

    session = LearningSession(user_id=regular_user.id, topic_name="seq")
    test_db_session.add(session)
    test_db_session.flush()
    _add_log(
        test_db_session, user_id=regular_user.id, label="want", symbol_id=None,
        position=0, session_id=session.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="cookie",
        symbol_id=cookie.id, position=1, session_id=session.id,
    )
    test_db_session.commit()

    service = SymbolAnalytics()
    first = service.get_history_transitions(regular_user.id, db=test_db_session)
    assert first[("want",)]["cookie"] == 1
    assert "milk" not in first[("want",)]

    # New usage invalidates and rebuilds the index on the next read.
    milk = Symbol(label="milk", category="noun", language="en")
    test_db_session.add(milk)
    test_db_session.flush()
    session_two = LearningSession(user_id=regular_user.id, topic_name="seq2")
    test_db_session.add(session_two)
    test_db_session.flush()
    _add_log(
        test_db_session, user_id=regular_user.id, label="want", symbol_id=None,
        position=0, session_id=session_two.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="milk",
        symbol_id=milk.id, position=1, session_id=session_two.id,
    )
    test_db_session.commit()

    second = service.get_history_transitions(regular_user.id, db=test_db_session)
    assert second[("want",)]["cookie"] == 1
    assert second[("want",)]["milk"] == 1
