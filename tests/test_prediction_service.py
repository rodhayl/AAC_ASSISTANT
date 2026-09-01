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


def test_schedule_svg_generation_forwards_topic_as_context(
    test_db_session, regular_user, monkeypatch
):
    """Homonym pictograms must receive the learning topic as disambiguation
    context, so "sierra" in a geography topic is drawn as a mountain range
    (and as a saw in a tools topic). Without a topic, no context is sent."""
    from src.aac_app.services import symbol_svg_autogen as autogen
    from src.aac_app.services.prediction_service import _PredictionContext

    calls: list[tuple] = []
    monkeypatch.setattr(
        autogen,
        "ensure_symbol_generated",
        lambda word, lang, context=None: calls.append((word, lang, context)),
    )

    service = _PredictionContext(
        user_id=regular_user.id,
        current_symbols=[],
        language="es",
        offset=0,
        base_limit=5,
        limit=5,
        board_id=None,
        db=test_db_session,
        analytics_service=Mock(),
        load_model=lambda lang: {"bigrams": {}},
        topic="geografía",
    )
    monkeypatch.setattr(service, "_is_svg_generation_enabled", lambda: True)
    service._schedule_svg_generation("sierra")
    assert calls == [("sierra", "es", "geografía")]

    # Smartbar requests without a topic degrade gracefully to no context.
    calls.clear()
    service2 = _PredictionContext(
        user_id=regular_user.id,
        current_symbols=[],
        language="es",
        offset=0,
        base_limit=5,
        limit=5,
        board_id=None,
        db=test_db_session,
        analytics_service=Mock(),
        load_model=lambda lang: {"bigrams": {}},
    )
    monkeypatch.setattr(service2, "_is_svg_generation_enabled", lambda: True)
    service2._schedule_svg_generation("llave")
    assert calls == [("llave", "es", None)]


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


def test_topic_words_tier_surfaces_text_only_words_when_catalog_misses(
    test_db_session, regular_user, monkeypatch
):
    """A topic outside the symbol catalog gets LLM words as text-only
    suggestions, so learners are never limited by the database symbols."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)

    # Catalog has nothing astrophysics-related.
    test_db_session.add_all(
        [
            Symbol(label="vaca", category="farm_animals", language="es", is_builtin=True),
            Symbol(label="cow", category="farm_animals", language="en", is_builtin=True),
        ]
    )
    test_db_session.commit()

    fetcher = Mock(return_value=["nebulosa", "supernova", "telescopio"])
    try:
        suggestions = service.predict_next(
            user_id=regular_user.id,
            current_symbols=[],
            limit=6,
            language="es",
            offset=0,
            topic="astrofísica",
            topic_word_fetcher=fetcher,
            db=test_db_session,
        )
    finally:
        from src.aac_app.services import prediction_service as ps_module

        ps_module._topics_word_cache.clear()

    ai_labels = [s["label"] for s in suggestions if s["source"] == "ai"]
    # The catalog miss falls back to the topic words first.
    assert ai_labels[:3] == ["nebulosa", "supernova", "telescopio"]
    for item in suggestions:
        if item["source"] == "ai":
            assert item.get("is_text_only") is True
            assert item.get("image_path") is None
            assert item.get("category") is None
            # Background pictogram generation is off in the test env, so the
            # tile must not claim a pictogram is being generated.
            assert item.get("is_generating") is False


def test_topic_words_tier_reattaches_catalog_symbols_before_text_only(
    test_db_session, regular_user, monkeypatch
):
    """A generated word that matches an existing symbol becomes a real
    suggestion (with image) rather than a text-only one."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)
    estrella = Symbol(
        label="estrella",
        category="science",
        language="es",
        image_path="/symbols/estrella.png",
        is_builtin=True,
    )
    test_db_session.add_all([estrella])
    test_db_session.commit()

    fetcher = Mock(return_value=["estrella", "planeta lejano"])
    try:
        suggestions = service.predict_next(
            user_id=regular_user.id,
            current_symbols=[],
            limit=6,
            language="es",
            offset=0,
            topic="astrofísica",
            topic_word_fetcher=fetcher,
            db=test_db_session,
        )
    finally:
        from src.aac_app.services import prediction_service as ps_module

        ps_module._topics_word_cache.clear()

    ai = [s for s in suggestions if s["source"] == "ai"]
    by_label = {s["label"]: s for s in ai}
    assert by_label["estrella"]["symbol_id"] == estrella.id
    assert by_label["estrella"]["image_path"] == "/symbols/estrella.png"
    assert by_label["estrella"].get("is_text_only") is not True
    assert by_label["planeta lejano"].get("is_text_only") is True


def test_topic_word_fetcher_is_cached_and_skipped_when_catalog_fully_covers(
    test_db_session, regular_user, monkeypatch
):
    """The LLM fetcher runs once per (language, topic) and is never called
    when the catalog tier alone already fills the requested slots."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)
    # Catalog fully covers this topic at limit=1 ("inteligencia artificial"
    # matches a token; "algoritmo" does not), so the fetcher must not run.
    test_db_session.add_all(
        [
            Symbol(label="inteligencia artificial", category="computing", language="es", keywords="IA", is_builtin=True),
            Symbol(label="algoritmo", category="computing", language="es", keywords="IA", is_builtin=True),
        ]
    )
    test_db_session.commit()
    fetcher = Mock(side_effect=AssertionError("fetcher must not be called"))

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=1,
        language="es",
        offset=0,
        topic="Inteligencia Artificial",
        topic_word_fetcher=fetcher,
        db=test_db_session,
    )
    assert any(s["source"] == "topic" for s in suggestions)
    assert not any(s.get("is_text_only") for s in suggestions)
    fetcher.assert_not_called()

    # Uncached miss path: fetcher is consulted once per (lang, topic); repeated
    # predict_next calls reuse the TTL cache instead of re-calling the LLM.
    fetcher2 = Mock(return_value=["nebulosa", "quasar"])
    try:
        for _ in range(3):
            service.predict_next(
                user_id=regular_user.id,
                current_symbols=[],
                limit=4,
                language="es",
                offset=0,
                topic="astrofísica",
                topic_word_fetcher=fetcher2,
                db=test_db_session,
            )
    finally:
        from src.aac_app.services import prediction_service as ps_module

        ps_module._topics_word_cache.clear()

    assert fetcher2.call_count == 1


def test_topic_words_tier_keeps_filling_when_catalog_only_partially_covers(
    test_db_session, regular_user, monkeypatch
):
    """Once the first generated pictogram lands in the catalog the topic tier
    produces some symbols, but the still-pending topic words must keep
    appearing (text-only) so their tiles upgrade in place instead of
    vanishing mid-generation."""
    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)
    # Partial coverage: one symbol matches the topic token "cuántica", the
    # rest of the topic vocabulary is still missing.
    test_db_session.add_all(
        [
            Symbol(
                label="gravedad cuántica",
                category="science",
                language="es",
                image_path="/symbols/gravedad.png",
                is_builtin=False,
            ),
            Symbol(label="vaca", category="farm_animals", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()

    fetcher = Mock(return_value=["agujero negro", "materia oscura", "teoría de cuerdas"])
    try:
        suggestions = service.predict_next(
            user_id=regular_user.id,
            current_symbols=[],
            limit=6,
            language="es",
            offset=0,
            topic="astrofísica cuántica",
            topic_word_fetcher=fetcher,
            db=test_db_session,
        )
    finally:
        from src.aac_app.services import prediction_service as ps_module

        ps_module._topics_word_cache.clear()

    # The catalog symbol shows as a topic-tier suggestion WITH its image...
    topic_item = next(s for s in suggestions if s["source"] == "topic")
    assert topic_item["label"] == "gravedad cuántica"
    assert topic_item["image_path"] == "/symbols/gravedad.png"
    # ...and the still-missing words keep appearing as text-only, so the
    # Smartbar never loses the pending tiles mid-generation.
    ai = [s for s in suggestions if s["source"] == "ai"]
    assert [s["label"] for s in ai] == ["agujero negro", "materia oscura", "teoría de cuerdas"]
    assert all(s.get("is_text_only") for s in ai)


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
