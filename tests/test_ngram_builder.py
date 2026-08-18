"""Tests for rebuilding n-gram prediction models from real usage logs."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src import config
from src.aac_app.models import LearningSession, Symbol, SymbolUsageLog
from src.aac_app.services import ngram_builder
from src.aac_app.services.ngram_builder import (
    collect_usage_bigrams,
    rebuild_ngram_models,
)
from src.aac_app.services.prediction_service import PredictionService


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


@pytest.fixture
def ngrams_data_dir(tmp_path: Path, monkeypatch):
    """Point the writable data/ngrams directory at a temp dir for the test."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        config, "DATABASE_PATH", tmp_path / "test.sqlite3"
    )
    return tmp_path


def _seed_symbols_and_logs(test_db_session, regular_user):
    """Seed en/es symbols and a realistic usage history."""
    want = Symbol(label="want", category="verb", language="en", image_path="want.png")
    cookie = Symbol(label="cookie", category="noun", language="en", image_path="cookie.png")
    milk = Symbol(label="milk", category="noun", language="en", image_path="milk.png")
    quiero = Symbol(label="quiero", category="verb", language="es", image_path="quiero.png")
    galleta = Symbol(label="galleta", category="noun", language="es", image_path="galleta.png")
    test_db_session.add_all([want, cookie, milk, quiero, galleta])
    test_db_session.flush()

    session_one = LearningSession(user_id=regular_user.id, topic_name="one")
    session_two = LearningSession(user_id=regular_user.id, topic_name="two")
    test_db_session.add_all([session_one, session_two])
    test_db_session.flush()

    # English: "want cookie" twice, "want milk" once (same session = one utterance
    # each in separate sessions so counts stay separate).
    _add_log(
        test_db_session, user_id=regular_user.id, label="want",
        symbol_id=want.id, position=0, session_id=session_one.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="cookie",
        symbol_id=cookie.id, position=1, session_id=session_one.id,
    )
    session_three = LearningSession(user_id=regular_user.id, topic_name="three")
    test_db_session.add(session_three)
    test_db_session.flush()
    _add_log(
        test_db_session, user_id=regular_user.id, label="want",
        symbol_id=want.id, position=0, session_id=session_three.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="cookie",
        symbol_id=cookie.id, position=1, session_id=session_three.id,
    )
    session_four = LearningSession(user_id=regular_user.id, topic_name="four")
    test_db_session.add(session_four)
    test_db_session.flush()
    _add_log(
        test_db_session, user_id=regular_user.id, label="want",
        symbol_id=want.id, position=0, session_id=session_four.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="milk",
        symbol_id=milk.id, position=1, session_id=session_four.id,
    )

    # Spanish: "quiero galleta" once.
    session_five = LearningSession(user_id=regular_user.id, topic_name="five")
    test_db_session.add(session_five)
    test_db_session.flush()
    _add_log(
        test_db_session, user_id=regular_user.id, label="quiero",
        symbol_id=quiero.id, position=0, session_id=session_five.id,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="galleta",
        symbol_id=galleta.id, position=1, session_id=session_five.id,
    )
    test_db_session.commit()
    return want, cookie, milk


def test_collect_usage_bigrams_groups_by_locale_and_session(
    test_db_session, regular_user
):
    """Real logs produce per-locale (prefix, next) counts segmented by utterance."""
    _seed_symbols_and_logs(test_db_session, regular_user)

    learned = collect_usage_bigrams(db=test_db_session)

    assert learned["en"][("want", "cookie")] == 2
    assert learned["en"][("want", "milk")] == 1
    assert learned["es"][("quiero", "galleta")] == 1
    assert "en" not in learned or ("quiero", "galleta") not in learned.get("en", {})


def test_rebuild_ngram_models_writes_fused_models(
    test_db_session, regular_user, ngrams_data_dir, monkeypatch
):
    """Rebuilt models fuse learned transitions over the bundled seed."""
    monkeypatch.setattr(ngram_builder, "DEFAULT_LOCALES", ("en",))
    _seed_symbols_and_logs(test_db_session, regular_user)

    written = rebuild_ngram_models(db=test_db_session, locales=("en",))

    path = written["en"]
    assert path == ngrams_data_dir / "ngrams" / "en.json"
    assert path.exists()

    with open(path, encoding="utf-8") as handle:
        model = json.load(handle)
    bigrams = model["bigrams"]
    # Learned transition present with probability 2/3.
    assert bigrams["want"]["cookie"] == pytest.approx(2 / 3, abs=0.001)
    assert bigrams["want"]["milk"] == pytest.approx(1 / 3, abs=0.001)
    # Bundled seed entries (e.g. "i" -> "want") survive the fusion.
    assert "i" in bigrams
    assert "want" in bigrams["i"]


def test_rebuild_ngram_models_does_not_touch_bundled_files(
    test_db_session, regular_user, ngrams_data_dir, monkeypatch
):
    """The bundled seed JSON is never modified by a rebuild."""
    bundled = config.get_ngrams_path() / "en.json"
    original = bundled.read_text(encoding="utf-8")
    monkeypatch.setattr(ngram_builder, "DEFAULT_LOCALES", ("en",))
    _seed_symbols_and_logs(test_db_session, regular_user)

    rebuild_ngram_models(db=test_db_session, locales=("en",))

    assert bundled.read_text(encoding="utf-8") == original
    assert not (ngrams_data_dir / "ngrams" / "es.json").exists()


def test_prediction_service_prefers_rebuilt_model(
    test_db_session, regular_user, ngrams_data_dir, monkeypatch
):
    """_load_model reads data/ngrams over the bundled seed after a rebuild."""
    monkeypatch.setattr(ngram_builder, "DEFAULT_LOCALES", ("en",))
    _seed_symbols_and_logs(test_db_session, regular_user)
    rebuild_ngram_models(db=test_db_session, locales=("en",))

    service = PredictionService()
    service._models.clear()
    model = service._load_model("en")

    # The learned "want -> cookie/milk" transition wins over the bundled file,
    # which never had a "want" prefix with exactly these probabilities.
    assert model["bigrams"]["want"]["cookie"] == pytest.approx(2 / 3, abs=0.001)
    assert model["bigrams"]["want"]["milk"] == pytest.approx(1 / 3, abs=0.001)


def test_rebuild_invalidates_prediction_cache(
    test_db_session, regular_user, ngrams_data_dir, monkeypatch
):
    """A rebuild drops the singleton's cached model so the next read refreshes."""
    monkeypatch.setattr(ngram_builder, "DEFAULT_LOCALES", ("en",))
    _seed_symbols_and_logs(test_db_session, regular_user)

    service = PredictionService()
    service._models.clear()
    # Prime the cache with the bundled seed (learned probability is 2/3).
    before = service._load_model("en")
    assert before["bigrams"]["want"]["cookie"] == 1.0

    rebuild_ngram_models(db=test_db_session, locales=("en",))

    after = service._load_model("en")
    assert after["bigrams"]["want"]["cookie"] == pytest.approx(2 / 3, abs=0.001)


def test_rebuild_ngram_models_ignores_single_symbol_logs(
    test_db_session, regular_user, ngrams_data_dir, monkeypatch
):
    """Utterances shorter than two symbols produce no bigrams."""
    monkeypatch.setattr(ngram_builder, "DEFAULT_LOCALES", ("en",))
    symbol = Symbol(label="solo", category="test", language="en")
    test_db_session.add(symbol)
    test_db_session.flush()
    _add_log(
        test_db_session, user_id=regular_user.id, label="solo",
        symbol_id=symbol.id, position=0,
    )
    test_db_session.commit()

    learned = collect_usage_bigrams(db=test_db_session)
    assert learned == {}


def test_single_symbol_utterances_do_not_chain_without_session(
    test_db_session, regular_user, monkeypatch
):
    """Position resets split consecutive single-symbol logs into separate utterances.

    The real usage table stores every selection of a one-symbol utterance as
    position 0 with no session id; those must never be joined into a fake
    sequence just because timestamps are close together.
    """
    symbol = Symbol(label="solo", category="test", language="en")
    test_db_session.add(symbol)
    test_db_session.flush()
    start = datetime(2024, 1, 1, 12, 0, 0)
    for index in range(3):
        _add_log(
            test_db_session, user_id=regular_user.id, label="solo",
            symbol_id=symbol.id, position=0,
            timestamp=start + timedelta(seconds=index),
        )
    test_db_session.commit()

    learned = collect_usage_bigrams(db=test_db_session)
    assert learned == {}


def test_position_advance_keeps_utterance_together(
    test_db_session, regular_user, monkeypatch
):
    """Increasing positions inside one session form real bigrams."""
    want = Symbol(label="want", category="verb", language="en")
    cookie = Symbol(label="cookie", category="noun", language="en")
    test_db_session.add_all([want, cookie])
    test_db_session.flush()
    start = datetime(2024, 1, 1, 12, 0, 0)
    _add_log(
        test_db_session, user_id=regular_user.id, label="want",
        symbol_id=want.id, position=0, timestamp=start,
    )
    _add_log(
        test_db_session, user_id=regular_user.id, label="cookie",
        symbol_id=cookie.id, position=1, timestamp=start + timedelta(seconds=1),
    )
    test_db_session.commit()

    learned = collect_usage_bigrams(db=test_db_session)
    assert learned["en"][("want", "cookie")] == 1
