from unittest.mock import Mock

from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol
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
    monkeypatch.setattr(board_helpers, "_GoogleTranslator", translator_class)
    monkeypatch.setattr(board_helpers, "_translation_import_attempted", True)
    board_helpers._build_symbol_translator.cache_clear()

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
        board_helpers._build_symbol_translator.cache_clear()

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
