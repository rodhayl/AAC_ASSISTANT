import contextlib
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


def _reset_translation_state() -> None:
    runtime_translation._translate_cached.cache_clear()
    with runtime_translation._circuit_lock:
        runtime_translation._consecutive_failures = 0
        runtime_translation._circuit_open_until = 0.0


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
        offset=0,
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
    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

        def json(self):
            return [[[{"Hello": "Hola", "Hello there": "Hola allí"}[self.text], self.text]]]

    class FakeClient:
        def __init__(self, **_kwargs):
            self.text = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url, *, params):
            return FakeResponse(params["q"])

    translator_factory = Mock(side_effect=lambda **kwargs: FakeClient(**kwargs))
    monkeypatch.setattr(runtime_translation, "_translation_client_factory", translator_factory)
    _reset_translation_state()

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
        _reset_translation_state()

    assert translator_factory.call_count == 2
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
    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

        def json(self):
            return [[[{"Hello": "Hola", "Hello there": "Hola allí"}[self.text], self.text]]]

    class FakeClient:
        def __init__(self, **_kwargs):
            self.text = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url, *, params):
            return FakeResponse(params["q"])

    translator_factory = Mock(side_effect=lambda **kwargs: FakeClient(**kwargs))
    monkeypatch.setattr(runtime_translation, "_translation_client_factory", translator_factory)
    _reset_translation_state()

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
        _reset_translation_state()

    assert translator_factory.call_count == 2
    assert payload["symbols"][0]["custom_text"] == "Hola allí"
    assert payload["symbols"][0]["symbol"]["label"] == "Hola"


def test_runtime_translation_uses_bounded_trusted_endpoint(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [[['Hola', 'Hello']]]

    class Client:
        def __init__(self, **kwargs):
            captured['kwargs'] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, *, params):
            captured['url'] = url
            captured['params'] = params
            return Response()

    factory = Mock(side_effect=lambda **kwargs: Client(**kwargs))
    monkeypatch.setattr(runtime_translation, '_translation_client_factory', factory)
    _reset_translation_state()

    assert runtime_translation.translate_text('Hello', 'es-ES') == 'Hola'
    assert captured['url'] == 'https://translate.googleapis.com/translate_a/single'
    assert captured['params'] == {
        'client': 'gtx',
        'sl': 'auto',
        'tl': 'es',
        'dt': 't',
        'q': 'Hello',
    }
    assert captured['kwargs']['follow_redirects'] is False
    assert captured['kwargs']['headers']['User-Agent'] == 'AAC-Assistant/2.0'
    assert captured['kwargs']['timeout'].connect == 3.0
    assert captured['kwargs']['timeout'].read == 3.0


def test_runtime_translation_rejects_malformed_response_and_opens_circuit(monkeypatch):
    class MalformedResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'unexpected': 'shape'}

    class MalformedClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return MalformedResponse()

    factory = Mock(side_effect=lambda **kwargs: MalformedClient(**kwargs))
    monkeypatch.setattr(runtime_translation, '_translation_client_factory', factory)
    _reset_translation_state()

    for text in ('one', 'two', 'three', 'four'):
        with contextlib.suppress(RuntimeError):
            runtime_translation.translate_text(text, 'es')
    assert factory.call_count == 3


def test_runtime_translation_times_out_and_recovers_after_cooldown(monkeypatch):
    class HangingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            import time

            time.sleep(0.2)

    clock = [100.0]
    factory = Mock(side_effect=lambda **kwargs: HangingClient(**kwargs))
    monkeypatch.setattr(runtime_translation, '_translation_client_factory', factory)
    monkeypatch.setattr(runtime_translation, '_TRANSLATION_TIMEOUT_SECONDS', 0.01)
    monkeypatch.setattr(runtime_translation, '_CIRCUIT_BREAK_COOLDOWN_SECONDS', 10.0)
    monkeypatch.setattr(runtime_translation.time, 'monotonic', lambda: clock[0])
    _reset_translation_state()

    for text in ('one', 'two', 'three', 'four'):
        with contextlib.suppress(RuntimeError):
            runtime_translation.translate_text(text, 'es')
    # The open circuit suppresses network work during its cooldown.
    assert factory.call_count == 3

    # Once the cooldown expires, translation attempts resume.
    clock[0] = 111.0
    with contextlib.suppress(RuntimeError):
        runtime_translation.translate_text('four', 'es')
    assert factory.call_count == 4


def test_prediction_service_keeps_suggestions_in_requested_language(
    test_db_session, regular_user
):
    """History suggestions from another locale are not mixed into the Smartbar."""
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

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=5,
        language="es-ES",
        offset=0,
        db=test_db_session,
    )

    assert suggestions
    assert all(suggestion["label"] != "cookie" for suggestion in suggestions)
    assert all(suggestion["source"] != "history" for suggestion in suggestions)
