"""Tests for rebuilding n-gram prediction models from real usage logs."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src import config
from src.aac_app.models import LearningSession, Symbol, SymbolUsageLog, User
from src.aac_app.services import ngram_builder
from src.aac_app.services.ngram_builder import (
    collect_usage_bigrams,
    rebuild_ngram_models,
    run_periodic_ngram_rebuild,
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


def test_collect_usage_bigrams_does_not_join_anonymous_logs_across_users(
    test_db_session, regular_user
):
    """Anonymous legacy logs from different users cannot form one phrase."""
    want = Symbol(label="want", category="verb", language="en")
    cookie = Symbol(label="cookie", category="noun", language="en")
    other_user = User(
        username="ngram_other_user",
        password_hash="test",
        display_name="Other Ngram User",
        user_type="standard",
        is_active=True,
    )
    test_db_session.add_all([want, cookie, other_user])
    test_db_session.flush()

    start = datetime(2024, 1, 1, 12, 0, 0)
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="want",
        symbol_id=want.id,
        position=0,
        timestamp=start,
    )
    _add_log(
        test_db_session,
        user_id=other_user.id,
        label="cookie",
        symbol_id=cookie.id,
        position=1,
        timestamp=start + timedelta(seconds=1),
    )
    test_db_session.commit()

    assert collect_usage_bigrams(db=test_db_session) == {}


def test_collect_usage_bigrams_splits_locale_changes_within_a_session(
    test_db_session, regular_user
):
    """A reused session cannot create a cross-language transition."""
    want = Symbol(label="want", category="verb", language="en")
    cookie = Symbol(label="cookie", category="noun", language="en")
    quiero = Symbol(label="quiero", category="verb", language="es")
    galleta = Symbol(label="galleta", category="noun", language="es")
    test_db_session.add_all([want, cookie, quiero, galleta])
    test_db_session.flush()

    session = LearningSession(user_id=regular_user.id, topic_name="mixed-locale")
    test_db_session.add(session)
    test_db_session.flush()
    start = datetime(2024, 1, 1, 12, 0, 0)
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="want",
        symbol_id=want.id,
        position=0,
        session_id=session.id,
        timestamp=start,
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="cookie",
        symbol_id=cookie.id,
        position=1,
        session_id=session.id,
        timestamp=start + timedelta(seconds=1),
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="quiero",
        symbol_id=quiero.id,
        position=2,
        session_id=session.id,
        timestamp=start + timedelta(seconds=2),
    )
    _add_log(
        test_db_session,
        user_id=regular_user.id,
        label="galleta",
        symbol_id=galleta.id,
        position=3,
        session_id=session.id,
        timestamp=start + timedelta(seconds=3),
    )
    test_db_session.commit()

    learned = collect_usage_bigrams(db=test_db_session)

    assert learned["en"][("want", "cookie")] == 1
    assert learned["es"][("quiero", "galleta")] == 1
    assert ("cookie", "quiero") not in learned["en"]
    assert ("cookie", "quiero") not in learned["es"]


def test_rebuild_ngram_models_preserves_previous_file_when_serialization_fails(
    test_db_session, regular_user, ngrams_data_dir, monkeypatch
):
    """A failed rebuild never exposes a truncated replacement model."""
    output_dir = ngrams_data_dir / "ngrams"
    output_dir.mkdir(parents=True)
    output_path = output_dir / "en.json"
    previous = '{"bigrams": {"old": {"value": 1.0}}}\n'
    output_path.write_text(previous, encoding="utf-8")

    def fail_dump(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ngram_builder.json, "dump", fail_dump)

    with pytest.raises(OSError, match="disk full"):
        rebuild_ngram_models(db=test_db_session, locales=("en",))

    assert output_path.read_text(encoding="utf-8") == previous
    assert list(output_dir.glob(".en.*.tmp")) == []


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


async def _run_until_rebuilt(
    rebuild_fn, interval_seconds: int, *, run_for: float, locales=("en",)
):
    """Run the periodic loop for a short wall-clock window and cancel it."""
    task = asyncio.create_task(
        run_periodic_ngram_rebuild(
            locales, interval_seconds=interval_seconds, rebuild_fn=rebuild_fn
        )
    )
    await asyncio.sleep(run_for)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_periodic_rebuild_runs_multiple_times():
    """A positive interval rebuilds immediately and again after each sleep."""
    calls: list[tuple[object, tuple[str, ...]]] = []

    def fake_rebuild(db, locales):
        calls.append((db, locales))

    asyncio.run(_run_until_rebuilt(fake_rebuild, interval_seconds=1, run_for=2.3))

    # First call is immediate, then one per interval tick within the window.
    assert len(calls) >= 3
    assert all(locales == ("en",) for _, locales in calls)


def test_periodic_rebuild_survives_transient_failure():
    """A failing iteration is logged and the loop keeps rebuilding."""
    calls: list[int] = []

    def flaky_rebuild(db, locales):
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("transient database lock")

    asyncio.run(_run_until_rebuilt(flaky_rebuild, interval_seconds=1, run_for=2.2))

    assert len(calls) >= 2  # second iteration succeeded after the failure


def test_periodic_rebuild_stops_on_non_positive_interval():
    """interval <= 0 performs the single startup rebuild and returns."""
    calls: list[tuple[object, tuple[str, ...]]] = []

    def fake_rebuild(db, locales):
        calls.append((db, locales))

    asyncio.run(
        run_periodic_ngram_rebuild(
            ("en",), interval_seconds=0, rebuild_fn=fake_rebuild
        )
    )

    assert len(calls) == 1


def test_periodic_rebuild_passes_locales_through():
    """The configured locale tuple is forwarded to every rebuild call."""
    received: list[tuple[str, ...]] = []

    def fake_rebuild(db, locales):
        received.append(locales)

    asyncio.run(
        _run_until_rebuilt(fake_rebuild, interval_seconds=1, run_for=1.1, locales=("es", "en"))
    )

    assert len(received) >= 2
    assert all(locales == ("es", "en") for locales in received)


def test_periodic_rebuild_cancel_during_inflight_worker():
    """Cancelling while a rebuild runs in a thread drains without a dangling task.

    The shutdown path cancels the periodic task, which may be mid-rebuild in an
    ``asyncio.to_thread`` worker. The wrapper must surface CancelledError and
    finish; the thread worker is allowed to finish on its own (it is isolated
    from the event loop), but the loop must not schedule a next iteration.
    """
    import threading

    worker_reached = threading.Event()
    release_worker = threading.Event()
    rebuilds_started = 0

    def slow_rebuild(db, locales):
        nonlocal rebuilds_started
        rebuilds_started += 1
        worker_reached.set()
        release_worker.wait(timeout=5)

    async def scenario() -> None:
        task = asyncio.create_task(
            run_periodic_ngram_rebuild(
                ("en",), interval_seconds=1, rebuild_fn=slow_rebuild
            )
        )
        # Wait until the first rebuild is running inside the thread pool.
        while rebuilds_started == 0:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # The periodic task is fully drained; only this test's own task remains.
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())

    # The worker may still be running; let it finish so the thread pool drains.
    release_worker.set()
    assert rebuilds_started == 1  # no second iteration was scheduled


def test_lifespan_cancels_periodic_ngram_rebuild_on_shutdown(monkeypatch):
    """The real lifespan cancels the periodic task at shutdown, no errors.

    Starts the production ASGI app via TestClient (which runs the full lifespan
    startup and shutdown), with the periodic n-gram task enabled on a 1s
    interval. After the context exits, the loop must have stopped scheduling
    rebuilds and the server must have shut down cleanly.
    """
    import time as time_module

    from fastapi.testclient import TestClient

    from src.api import main as main_module
    from src.api.main import app

    calls: list[tuple[str, ...]] = []

    async def fake_periodic(locales, interval_seconds=3600):
        while True:
            calls.append(locales)
            await asyncio.sleep(interval_seconds)

    # Activate the periodic task; keep the other startup work inert so the
    # lifespan is fast and touches no network.
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("AAC_ENABLE_NGRAM_REBUILD", "true")
    monkeypatch.setenv("AAC_NGRAM_REBUILD_INTERVAL_SECONDS", "1")
    monkeypatch.setattr(main_module, "run_periodic_ngram_rebuild", fake_periodic)
    monkeypatch.setattr(main_module, "warmup_providers", lambda *a, **kw: None)
    monkeypatch.setattr(main_module, "index_all_symbols", lambda *a, **kw: None)

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        # Wait for the periodic loop to run at least twice.
        deadline = time_module.monotonic() + 8
        while len(calls) < 2 and time_module.monotonic() < deadline:
            time_module.sleep(0.05)
        assert len(calls) >= 2

    # After shutdown the loop must have stopped scheduling new rebuilds.
    time_module.sleep(1.3)
    after_shutdown = len(calls)
    time_module.sleep(1.3)
    assert len(calls) == after_shutdown


def test_resolve_log_language_matches_stored_labels_literally(test_db_session):
    """A '%' or '_' inside a logged label cannot wildcard-match another symbol.

    Logs without a linked symbol are attributed by matching their stored
    label against the catalog. Before escaping, a ``_`` in the log label
    matched any single character and a ``%`` matched any prefix, attributing
    logs to the wrong locale (or to any locale at all when no literal
    symbol exists).
    """
    from types import SimpleNamespace

    from src.aac_app.services import ngram_builder

    test_db_session.add_all(
        [
            Symbol(label="washXhands", category="verb", language="es", is_builtin=True),
            # The literal label of the log used below: exists only in en.
            Symbol(label="wash_hands", category="verb", language="en", is_builtin=True),
            # Prefix "50" exists (es), but the literal label "50%" does not.
            Symbol(label="50", category="number", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()

    # '_' in the log label must not prefer the es "washXhands" wildcard match;
    # the literal en symbol is the only correct attribution.
    underscore_log = SimpleNamespace(symbol_id=None, symbol_label="wash_hands")
    assert ngram_builder._resolve_log_language(test_db_session, underscore_log) == "en"

    # '%' in the log label must not act as a prefix wildcard over "50": no
    # literal "50%" symbol exists anywhere, so the log is unattributed.
    percent_log = SimpleNamespace(symbol_id=None, symbol_label="50%")
    assert ngram_builder._resolve_log_language(test_db_session, percent_log) is None
