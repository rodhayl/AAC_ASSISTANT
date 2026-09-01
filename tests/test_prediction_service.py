"""Focused regression tests for PredictionService symbol-library handling."""

from unittest.mock import Mock

import pytest
from sqlalchemy import event

from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol
from src.aac_app.services.prediction_service import (
    PredictionService,
    _label_looks_bad,
    _tokenize_topic,
)


def test_warmup_builds_symbol_catalog(test_db_session, regular_user, monkeypatch):
    """warmup() builds the cached catalog so the first prediction is fast."""
    from src.aac_app.services.prediction_service import _catalog_cache

    service = PredictionService()
    test_db_session.add_all(
        [
            Symbol(label="cookie", category="noun", language="en", is_builtin=True),
            Symbol(label="galleta", category="noun", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()

    service.warmup(db=test_db_session)

    bind = test_db_session.get_bind()
    cached = _catalog_cache.get(bind)
    assert cached is not None
    assert "cookie" in cached
    assert "galleta" in cached

    # A prediction against the same engine must reuse the warmed catalog
    # instead of scanning the symbols table again. The catalog scan is the
    # only query with this distinctive filter, so its absence proves reuse
    # regardless of the analytics reads and n-gram model contents.
    statements: list[str] = []

    def record_statement(sql, *_args):
        statements.append(str(sql))

    event.listen(test_db_session.bind, "before_cursor_execute", record_statement)
    try:
        service.predict_next(
            user_id=regular_user.id,
            current_symbols=[{"label": "want"}],
            limit=5,
            language="en",
            offset=0,
            db=test_db_session,
        )
    finally:
        event.remove(test_db_session.bind, "before_cursor_execute", record_statement)

    assert not any("label IS NOT NULL" in sql for sql in statements)


def test_predict_next_loads_symbol_library_once_per_request(
    test_db_session, regular_user, monkeypatch
):
    """One library load serves both resolve paths; per-word ilike queries are gone."""
    service = PredictionService()
    test_db_session.add_all(
        [
            Symbol(label="cookie", category="noun", language="en", is_builtin=True),
            Symbol(label="galleta", category="noun", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()
    monkeypatch.setitem(
        service._models,
        "en",
        {"bigrams": {"want": {"cookie": 1.0, "galleta": 0.5, "milk": 0.25}}},
    )

    user_id = regular_user.id
    statement_count = 0

    def count_statements(*_args):
        nonlocal statement_count
        statement_count += 1

    event.listen(test_db_session.bind, "before_cursor_execute", count_statements)
    try:
        suggestions = service.predict_next(
            user_id=user_id,
            current_symbols=[{"label": "want"}],
            limit=5,
            language="en",
            offset=0,
            db=test_db_session,
        )
    finally:
        event.remove(test_db_session.bind, "before_cursor_execute", count_statements)

    # analytics transition query + analytics empty-history query + one library
    # load. The bigram and standard-library resolve paths reuse that load.
    assert statement_count == 3

    labels = [suggestion["label"] for suggestion in suggestions]
    assert labels[0] == "cookie"
    assert "galleta" not in labels
    assert suggestions[0]["source"] == "general_model"


def test_predict_next_caches_symbol_catalog_between_requests(
    test_db_session, regular_user, monkeypatch
):
    """The catalog is cached per engine; a second call skips the library query."""
    service = PredictionService()
    monkeypatch.setitem(
        service._models,
        "en",
        {"bigrams": {"want": {"cookie": 1.0}}},
    )
    test_db_session.add(
        Symbol(label="cookie", category="noun", language="en", is_builtin=True)
    )
    test_db_session.commit()

    user_id = regular_user.id
    statement_count = 0

    def count_statements(*_args):
        nonlocal statement_count
        statement_count += 1

    event.listen(test_db_session.bind, "before_cursor_execute", count_statements)
    try:
        service.predict_next(
            user_id=user_id,
            current_symbols=[{"label": "want"}],
            limit=5,
            language="en",
            offset=0,
            db=test_db_session,
        )
        first_count = statement_count
        suggestions = service.predict_next(
            user_id=user_id,
            current_symbols=[{"label": "want"}],
            limit=5,
            language="en",
            offset=0,
            db=test_db_session,
        )
    finally:
        event.remove(test_db_session.bind, "before_cursor_execute", count_statements)

    # The catalog loads once; the cached second call skips the library query
    # and only repeats the two analytics reads.
    assert first_count == 3
    assert statement_count == first_count + 2
    assert suggestions[0]["label"] == "cookie"


def test_predict_next_pagination_skips_seen_suggestions(
    test_db_session, regular_user, monkeypatch
):
    """A non-zero offset continues after the previous page instead of repeating it."""
    service = PredictionService()
    test_db_session.add_all(
        [
            Symbol(label="one", category="noun", language="en", is_builtin=True),
            Symbol(label="two", category="noun", language="en", is_builtin=True),
            Symbol(label="three", category="noun", language="en", is_builtin=True),
            Symbol(label="four", category="noun", language="en", is_builtin=True),
            Symbol(label="five", category="noun", language="en", is_builtin=True),
        ]
    )
    test_db_session.commit()
    monkeypatch.setitem(
        service._models,
        "en",
        {
            "bigrams": {
                "want": {
                    "one": 1.0,
                    "two": 0.9,
                    "three": 0.8,
                    "four": 0.7,
                    "five": 0.6,
                }
            }
        },
    )

    user_id = regular_user.id
    page_one = service.predict_next(
        user_id=user_id,
        current_symbols=[{"label": "want"}],
        limit=2,
        language="en",
        offset=0,
        db=test_db_session,
    )
    page_two = service.predict_next(
        user_id=user_id,
        current_symbols=[{"label": "want"}],
        limit=2,
        language="en",
        offset=2,
        db=test_db_session,
    )

    labels_one = [s["label"] for s in page_one]
    labels_two = [s["label"] for s in page_two]
    assert labels_one == ["one", "two"]
    assert labels_two == ["three", "four"]
    assert not set(labels_one) & set(labels_two)


def test_predict_next_board_scope_uses_scalar_symbol_ids(
    test_db_session, regular_user, monkeypatch
):
    """Board-scoped fallbacks bind integer symbol IDs, not SQLAlchemy Row objects."""
    service = PredictionService()
    board = CommunicationBoard(
        name="Prediction board",
        user_id=regular_user.id,
        is_public=True,
    )
    symbol = Symbol(label="cookie", category="noun", language="en", is_builtin=True)
    test_db_session.add_all([board, symbol])
    test_db_session.commit()
    test_db_session.add(
        BoardSymbol(
            board_id=board.id,
            symbol_id=symbol.id,
            is_visible=True,
            position_x=0,
            position_y=0,
        )
    )
    test_db_session.commit()
    monkeypatch.setitem(service._models, "en", {"bigrams": {}})

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=5,
        language="en",
        offset=0,
        board_id=board.id,
        db=test_db_session,
    )

    assert any(
        suggestion["symbol_id"] == symbol.id for suggestion in suggestions
    )


def test_predict_next_new_symbols_visible_after_mutation(
    test_db_session, regular_user, monkeypatch
):
    """Mapper events invalidate the cached catalog so new symbols appear."""
    service = PredictionService()
    monkeypatch.setitem(
        service._models,
        "en",
        {"bigrams": {"want": {"milk": 1.0}}},
    )
    user_id = regular_user.id

    first = service.predict_next(
        user_id=user_id,
        current_symbols=[{"label": "want"}],
        limit=5,
        language="en",
        offset=0,
        db=test_db_session,
    )
    assert not any(suggestion["label"] == "milk" for suggestion in first)

    test_db_session.add(
        Symbol(label="milk", category="noun", language="en", is_builtin=True)
    )
    test_db_session.commit()

    second = service.predict_next(
        user_id=user_id,
        current_symbols=[{"label": "want"}],
        limit=5,
        language="en",
        offset=0,
        db=test_db_session,
    )
    assert any(suggestion["label"] == "milk" for suggestion in second)


def test_tokenize_topic_strips_stopwords_and_short_words():
    assert _tokenize_topic("Inteligencia Artificial y LLMs") == [
        "inteligencia",
        "artificial",
        "llms",
    ]
    assert _tokenize_topic("") == []
    assert _tokenize_topic("el y de a") == []


def test_predict_next_topic_surfaces_matching_symbols_first(
    test_db_session, regular_user, monkeypatch
):
    """A study topic must rank its matching catalog symbols before fallbacks."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    test_db_session.add_all(
        [
            Symbol(label="inteligencia artificial", category="computing", language="es", keywords="inteligencia artificial, IA", is_builtin=True),
            Symbol(label="coche", category="toy", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()

    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=5,
        language="es",
        offset=0,
        topic="Inteligencia Artificial y LLMs",
        db=test_db_session,
    )

    sources = [s["source"] for s in suggestions]
    assert sources[0] == "topic"
    labels = [s["label"] for s in suggestions]
    assert "inteligencia artificial" in labels
    # Topic match ranks first, ahead of any global fallback.
    assert suggestions[0]["label"] == "inteligencia artificial"


def test_topic_tier_ranks_word_boundary_label_matches_above_embedded_tokens(
    test_db_session, regular_user, monkeypatch
):
    """A label embedding a topic token ("fuegos artificiales") must not
    outrank a label containing the topic words at word boundaries."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    test_db_session.add_all(
        [
            Symbol(label="inteligencia artificial", category="computing", language="es", keywords="inteligencia artificial, IA", is_builtin=True),
            Symbol(label="fuegos artificiales", category="show", language="es", is_builtin=True),
            Symbol(label="ver los fuegos artificiales", category="verb", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()

    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=8,
        language="es",
        offset=0,
        topic="Inteligencia Artificial y LLMs",
        db=test_db_session,
    )

    topic_labels = [s["label"] for s in suggestions if s["source"] == "topic"]
    # The exact topic phrase outranks labels that merely embed one token, and
    # among the partial matches the shorter label wins.
    assert topic_labels == [
        "inteligencia artificial",
        "fuegos artificiales",
        "ver los fuegos artificiales",
    ]


def test_label_looks_bad_rejects_artifacts_and_paths():
    assert _label_looks_bad("frontend-icons")
    assert _label_looks_bad("node_modules/index")
    assert _label_looks_bad("dist/foo")
    assert _label_looks_bad("a/b")
    assert _label_looks_bad("a\\b")
    assert _label_looks_bad("x" * 51)
    assert _label_looks_bad("a-b-c-d-e")
    assert _label_looks_bad("")
    assert not _label_looks_bad("apple")
    assert not _label_looks_bad("ice-cream")


def test_predict_next_board_symbols_rank_before_global_history(test_db_session, regular_user, monkeypatch):
    """Board-scoped suggestions outrank global history/popular fallbacks.

    Regression: the board tier must run first so each board's suggestions
    reflect that board's symbols rather than the same global history on every
    board.
    """
    service = PredictionService()
    board = CommunicationBoard(
        name="Food board",
        user_id=regular_user.id,
        is_public=True,
    )
    board_symbol = Symbol(label="apple", category="food", language="en", is_builtin=True)
    off_board_symbol = Symbol(label="cookie", category="noun", language="en", is_builtin=True)
    test_db_session.add_all([board, board_symbol, off_board_symbol])
    test_db_session.commit()
    test_db_session.add(
        BoardSymbol(
            board_id=board.id,
            symbol_id=board_symbol.id,
            is_visible=True,
            position_x=0,
            position_y=0,
        )
    )
    test_db_session.commit()
    monkeypatch.setitem(service._models, "en", {"bigrams": {}})

    # Global history tier would otherwise return the off-board symbol first.
    analytics = Mock()
    analytics.suggest_next_symbol.side_effect = [
        [{"symbol_id": off_board_symbol.id, "label": "cookie", "category": "noun", "language": "en"}],  # history
        [],  # popular
    ]
    monkeypatch.setattr(service, "analytics_service", analytics)

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=3,
        language="en",
        offset=0,
        board_id=board.id,
        db=test_db_session,
    )

    sources = [s["source"] for s in suggestions]
    # The board-layout tier must fill the first slot with the board's symbol
    # before the global history tier adds its board-filtered candidate.
    assert suggestions[0]["source"] in {"board_layout", "board_popular", "board_personal"}
    assert "board_layout" in sources
    labels = [s["label"] for s in suggestions]
    assert "apple" in labels
    # The off-board history candidate is filtered out by the board scope.
    assert "cookie" not in labels


def test_predict_next_uses_popular_tier_when_history_and_ngrams_empty(
    test_db_session, regular_user, monkeypatch
):
    """Tier 3: popular global symbols interleave nouns and others."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "en", {"bigrams": {}})
    test_db_session.add_all(
        [
            Symbol(label="cookie", category="noun", language="en", is_builtin=True),
            Symbol(label="milk", category="food", language="en", is_builtin=True),
            Symbol(label="water", category="drink", language="en", is_builtin=True),
        ]
    )
    test_db_session.commit()

    analytics = Mock()
    analytics.suggest_next_symbol.side_effect = [
        [],  # history tier: no user history
        [                {"symbol_id": None, "label": "cookie", "category": "noun", "language": "en"},
                {"symbol_id": None, "label": "milk", "category": "food", "language": "en"},
                {"symbol_id": None, "label": "water", "category": "drink", "language": "en"},

        ],  # popular tier
    ]
    monkeypatch.setattr(service, "analytics_service", analytics)

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=3,
        language="en",
        offset=0,
        db=test_db_session,
    )

    sources = [s["source"] for s in suggestions]
    assert sources == ["popular", "popular", "popular"]
    # Interleaving keeps a noun first, then the others in order.
    assert suggestions[0]["category"] == "noun"


def test_predict_next_uses_standard_library_on_cold_start(
    test_db_session, regular_user, monkeypatch
):
    """Tier 4: cold start fills from the standard-library catalog labels."""
    from src.aac_app.services.symbol_catalog import standard_library_labels

    service = PredictionService()
    monkeypatch.setitem(service._models, "en", {"bigrams": {}})
    # Seed only symbols whose labels are in the standard library.
    standard = set(standard_library_labels("en"))
    chosen = sorted(standard)[:4]
    for label in chosen:
        test_db_session.add(
            Symbol(label=label, category="noun", language="en", is_builtin=True)
        )
    test_db_session.commit()

    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []  # no history, no popular
    monkeypatch.setattr(service, "analytics_service", analytics)

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=len(chosen),
        language="en",
        offset=0,
        db=test_db_session,
    )

    assert len(suggestions) >= 1
    assert all(s["source"] == "standard_library" for s in suggestions)
    assert {s["label"] for s in suggestions} <= set(chosen)


def test_predict_next_appends_punctuation_when_budget_allows(
    test_db_session, regular_user, monkeypatch
):
    """Tier 6: punctuation fills remaining slots past real suggestions."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "en", {"bigrams": {}})
    test_db_session.add(
        Symbol(label="cookie", category="noun", language="en", is_builtin=True)
    )
    test_db_session.commit()

    analytics = Mock()
    analytics.suggest_next_symbol.side_effect = [
        [],  # history tier: no user history
        [
            {"symbol_id": None, "label": "cookie", "category": "noun", "language": "en"}
        ],  # popular tier
    ]
    monkeypatch.setattr(service, "analytics_service", analytics)

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=3,
        language="en",
        offset=0,
        db=test_db_session,
    )

    sources = [s["source"] for s in suggestions]
    assert "popular" in sources
    assert "punctuation" in sources
    punct = [s for s in suggestions if s["source"] == "punctuation"]
    assert punct[0]["label"] == "."


def test_predict_next_popular_tier_failure_is_explicit(
    test_db_session, regular_user, monkeypatch
):
    """A failing analytics call during the popular tier raises, never fabricates."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "en", {"bigrams": {}})

    analytics = Mock()
    analytics.suggest_next_symbol.side_effect = [
        [],
        RuntimeError("analytics backend down"),
    ]
    monkeypatch.setattr(service, "analytics_service", analytics)

    with pytest.raises(RuntimeError, match="Popular symbol prediction failed"):
        service.predict_next(
            user_id=regular_user.id,
            current_symbols=[],
            limit=3,
            language="en",
            offset=0,
            db=test_db_session,
        )
