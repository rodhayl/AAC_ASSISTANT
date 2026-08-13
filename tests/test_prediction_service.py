"""Focused regression tests for PredictionService symbol-library handling."""

from sqlalchemy import event

from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol
from src.aac_app.services import prediction_service as prediction_module
from src.aac_app.services.prediction_service import PredictionService


def test_predict_next_loads_symbol_library_once_per_request(
    test_db_session, regular_user, monkeypatch
):
    """One library load serves both resolve paths; per-word ilike queries are gone."""
    service = PredictionService()
    monkeypatch.setattr(
        prediction_module, "translate_text", lambda text, _target_lang: text
    )
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
            offset=1,
            db=test_db_session,
        )
    finally:
        event.remove(test_db_session.bind, "before_cursor_execute", count_statements)

    # analytics transition query + analytics empty-history query + one library
    # load. The bigram and standard-library resolve paths reuse that load.
    assert statement_count == 3

    labels = [suggestion["label"] for suggestion in suggestions]
    assert labels[0] == "cookie"
    assert labels[1] == "galleta"
    assert suggestions[0]["source"] == "general_model"


def test_predict_next_caches_symbol_catalog_between_requests(
    test_db_session, regular_user, monkeypatch
):
    """The catalog is cached per engine; a second call skips the library query."""
    service = PredictionService()
    monkeypatch.setattr(
        prediction_module, "translate_text", lambda text, _target_lang: text
    )
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
            offset=1,
            db=test_db_session,
        )
        first_count = statement_count
        suggestions = service.predict_next(
            user_id=user_id,
            current_symbols=[{"label": "want"}],
            limit=5,
            language="en",
            offset=1,
            db=test_db_session,
        )
    finally:
        event.remove(test_db_session.bind, "before_cursor_execute", count_statements)

    # The catalog loads once; the cached second call skips the library query
    # and only repeats the two analytics reads.
    assert first_count == 3
    assert statement_count == first_count + 2
    assert suggestions[0]["label"] == "cookie"


def test_predict_next_board_scope_uses_scalar_symbol_ids(
    test_db_session, regular_user, monkeypatch
):
    """Board-scoped fallbacks bind integer symbol IDs, not SQLAlchemy Row objects."""
    service = PredictionService()
    monkeypatch.setattr(
        prediction_module, "translate_text", lambda text, _target_lang: text
    )
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
        offset=1,
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
        offset=1,
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
        offset=1,
        db=test_db_session,
    )
    assert any(suggestion["label"] == "milk" for suggestion in second)
