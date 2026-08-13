from unittest.mock import Mock

from src.aac_app.models import (
    BoardSymbol,
    CommunicationBoard,
    LearningSession,
    Symbol,
    SymbolUsageLog,
)
from src.aac_app.services import runtime_translation
from src.aac_app.services.prediction_service import PredictionService
from src.api.routers import board_helpers


def test_prediction_service_uses_bundled_spanish_ngrams(
    test_db_session, regular_user
):
    """Spanish transitions come from the bundled es.json n-gram model."""
    symbols = [
        Symbol(label=label, category="verb", language="es", is_builtin=True)
        for label in ("comer", "beber", "jugar")
    ]
    test_db_session.add_all(symbols)
    test_db_session.commit()

    service = PredictionService()
    service._models.pop("es", None)
    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[{"label": "quiero"}],
        limit=3,
        language="es-ES",
        offset=1,
        db=test_db_session,
    )

    assert [suggestion["label"] for suggestion in suggestions] == [
        "comer",
        "beber",
        "jugar",
    ]
    assert all(suggestion["source"] == "general_model" for suggestion in suggestions)


def test_spanish_board_translation_serializes_translated_symbol_payload(
    monkeypatch, test_db_session, regular_user
):
    """Board serialization translates Spanish labels while preserving its payload shape."""
    translator = Mock()
    translator.translate.side_effect = {
        "Hello": "Hola",
        "Hello there": "Hola allí",
    }.__getitem__
    translator_class = Mock(return_value=translator)
    monkeypatch.setattr(runtime_translation, "_GoogleTranslator", translator_class)
    monkeypatch.setattr(runtime_translation, "_translation_import_attempted", True)
    runtime_translation.clear_translation_cache()

    symbol = Symbol(
        label="Hello",
        description="A greeting",
        category="social",
        language="en",
        is_builtin=True,
    )
    board = CommunicationBoard(
        user_id=regular_user.id,
        name="Greetings",
        locale="en",
        is_language_learning=False,
    )
    board_symbol = BoardSymbol(
        board=board,
        symbol=symbol,
        position_x=1,
        position_y=2,
        custom_text="Hello there",
        is_visible=True,
    )
    test_db_session.add_all([symbol, board, board_symbol])
    test_db_session.flush()

    try:
        payload = board_helpers.serialize_board(board, target_lang="es")
    finally:
        runtime_translation.clear_translation_cache()

    translator_class.assert_called_once_with(source="auto", target="es")
    assert translator.translate.call_count == 2
    assert payload["name"] == "Greetings"
    assert payload["locale"] == "en"
    assert payload["is_language_learning"] is False
    assert payload["playable_symbols_count"] == 1
    assert len(payload["symbols"]) == 1
    assert {
        "id",
        "symbol_id",
        "position_x",
        "position_y",
        "size",
        "is_visible",
        "custom_text",
        "color",
        "linked_board_id",
        "symbol",
    } == set(payload["symbols"][0])
    assert payload["symbols"][0]["custom_text"] == "Hola allí"
    assert payload["symbols"][0]["symbol"]["label"] == "Hola"
    assert payload["symbols"][0]["symbol"]["category"] == "social"


def test_board_translation_normalizes_locale_style_target_language(
    monkeypatch, test_db_session, regular_user
):
    """Board translation accepts locale tags like es-ES without crashing."""
    translator = Mock()
    translator.translate.side_effect = {
        "Hello": "Hola",
        "Hello there": "Hola allí",
    }.__getitem__
    translator_class = Mock(return_value=translator)
    monkeypatch.setattr(runtime_translation, "_GoogleTranslator", translator_class)
    monkeypatch.setattr(runtime_translation, "_translation_import_attempted", True)
    runtime_translation.clear_translation_cache()

    symbol = Symbol(
        label="Hello",
        description="A greeting",
        category="social",
        language="en",
        is_builtin=True,
    )
    board = CommunicationBoard(
        user_id=regular_user.id,
        name="Greetings",
        locale="en",
        is_language_learning=False,
    )
    board_symbol = BoardSymbol(
        board=board,
        symbol=symbol,
        position_x=1,
        position_y=2,
        custom_text="Hello there",
        is_visible=True,
    )
    test_db_session.add_all([symbol, board, board_symbol])
    test_db_session.flush()

    try:
        payload = board_helpers.serialize_board(board, target_lang="es-ES")
    finally:
        runtime_translation.clear_translation_cache()

    translator_class.assert_called_once_with(source="auto", target="es")
    assert payload["symbols"][0]["custom_text"] == "Hola allí"
    assert payload["symbols"][0]["symbol"]["label"] == "Hola"


def test_prediction_service_localizes_history_labels_to_requested_language(
    monkeypatch, test_db_session, regular_user
):
    """History suggestions should be localized before they reach the smartbar."""
    service = PredictionService()
    symbol = Symbol(label="cookie", category="noun", language="en", is_builtin=True)
    session = LearningSession(
        user_id=regular_user.id,
        topic_name="practice",
        purpose="test",
    )
    test_db_session.add_all([symbol, session])
    test_db_session.flush()
    test_db_session.add(
        SymbolUsageLog(
            user_id=regular_user.id,
            session_id=session.id,
            symbol_id=symbol.id,
            symbol_label=symbol.label,
            symbol_category=symbol.category,
            position_in_utterance=0,
            utterance_length=1,
        )
    )
    test_db_session.commit()

    monkeypatch.setattr(
        "src.aac_app.services.prediction_service.translate_text",
        lambda text, target_lang: {"cookie": "galleta"}.get(text, text),
    )

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=5,
        language="es-ES",
        offset=1,
        db=test_db_session,
    )

    assert suggestions
    assert suggestions[0]["label"] == "galleta"
    assert suggestions[0]["source"] == "history"
