"""Tests for background SVG symbol auto-generation."""

import threading
from unittest.mock import patch

import pytest

from src.aac_app.models import Symbol
from src.aac_app.services import symbol_svg_autogen as autogen


@pytest.fixture(autouse=True)
def _reset_autogen_state(monkeypatch):
    """Isolate the module-level dedup sets between tests."""
    with autogen._lock:
        autogen._in_flight.clear()
        autogen._recent_failures.clear()
        autogen._rate_limited.clear()
    autogen._last_llm_call_at = 0.0
    # Keep unit tests fast: no real sleeps between LLM calls by default.
    monkeypatch.setattr(autogen, "_pacing_seconds", lambda: 0.0)
    autogen.set_llm_provider_factory(None)
    yield
    with autogen._lock:
        autogen._in_flight.clear()
        autogen._recent_failures.clear()
        autogen._rate_limited.clear()
    autogen._last_llm_call_at = 0.0
    autogen.set_llm_provider_factory(None)


def test_autogen_disabled_under_testing(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.delenv("AAC_AUTOGEN_SYMBOLS", raising=False)
    assert autogen.autogen_enabled() is False

    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("AAC_AUTOGEN_SYMBOLS", "1")
    assert autogen.autogen_enabled() is False

    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("AAC_AUTOGEN_SYMBOLS", "0")
    assert autogen.autogen_enabled() is False

    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("AAC_AUTOGEN_SYMBOLS", "1")
    assert autogen.autogen_enabled() is True


def test_ensure_generated_spawns_exactly_one_thread_for_duplicate_calls():
    """Concurrent calls for the same (label, language) start a single thread."""
    spawned: list[threading.Thread] = []

    def capturing_start(self):
        # Record the spawn only; never run the target so the test DB is not
        # touched by a real background thread.
        spawned.append(self)

    autogen.set_llm_provider_factory(lambda: None)

    # The daily budget check must not hit the DB in this isolated test.
    with patch.object(autogen, "_count_generated_today", return_value=0), patch.object(
        threading.Thread, "start", capturing_start
    ):
        autogen.ensure_symbol_generated("nebulosa", "es")
        autogen.ensure_symbol_generated("NEBULOSA", "es")
        autogen.ensure_symbol_generated("nebulosa", "es-ES")

    assert len(spawned) == 1
    assert spawned[0].name.startswith("svg-autogen-")


def test_ensure_generated_skips_empty_and_unknown_words():
    spawned: list[threading.Thread] = []

    def capturing_start(self):
        spawned.append(self)

    autogen.set_llm_provider_factory(lambda: None)
    with patch.object(threading.Thread, "start", capturing_start):
        autogen.ensure_symbol_generated("", "es")
        autogen.ensure_symbol_generated("   ", "es")
        autogen.ensure_symbol_generated("nebulosa", "")
        autogen.ensure_symbol_generated("nebulosa", None)  # type: ignore[arg-type]
    assert spawned == []


def test_background_generation_persists_symbol_and_svg(
    test_db_session, tmp_path, monkeypatch
):
    """A generated word becomes a real Symbol row with an SVG file."""
    from src import config
    from src.aac_app.db import get_session

    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path, raising=False)
    (tmp_path / "symbols").mkdir(parents=True, exist_ok=True)

    class _FakeProvider:
        def generate_sync(self, prompt, **kwargs) -> str:
            return (
                '{"background":"#ffffff",'
                '"shapes":[{"kind":"circle","cx":0,"cy":0,"r":60,"fill":"#FFD166"},'
                '{"kind":"circle","cx":0,"cy":0,"r":30,"fill":"#000000"}]}'
            )

    autogen.set_llm_provider_factory(lambda: _FakeProvider())
    key = autogen._PendingKey("nebulosa", "es")
    with autogen._lock:
        autogen._in_flight.add(key)
    with patch("src.aac_app.db.get_session", side_effect=get_session):
        # Route the module's lazy get_session imports through the real factory,
        # which reads DATABASE_URL set by the test fixture.
        autogen._generate_in_background(key, "nebulosa", "es")

    with autogen._lock:
        assert key not in autogen._in_flight

    row = test_db_session.query(Symbol).filter(Symbol.label == "nebulosa").first()
    assert row is not None
    assert row.language == "es"
    assert row.image_path.startswith("/uploads/symbols/")
    assert row.image_path.endswith(".png")
    saved = tmp_path / "symbols" / row.image_path.rsplit("/", 1)[1]
    assert saved.is_file()
    # Rasterized PNG (magic header), like every other symbol upload.
    assert saved.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_background_generation_skips_existing_symbol(
    test_db_session, tmp_path, monkeypatch
):
    """A word that already has a symbol is never regenerated."""
    from src import config
    from src.aac_app.db import get_session

    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path, raising=False)
    existing = Symbol(
        label="galaxia",
        category="space",
        language="es",
        image_path="/symbols/galaxia.png",
        is_builtin=True,
    )
    test_db_session.add(existing)
    test_db_session.commit()

    calls = []
    autogen.set_llm_provider_factory(lambda: None)
    # Force a fresh cache-free DB read via the test session's engine.
    with (
        patch.object(
            autogen,
            "_generate_sync_callable",
            side_effect=lambda: calls.append(1) or None,
        ),
        patch("src.aac_app.db.get_session", side_effect=get_session),
    ):
        key = autogen._PendingKey("galaxia", "es")
        autogen._generate_in_background(key, "galaxia", "es")

    assert calls == []  # Existing symbol -> no generation attempt.


def test_failed_generation_gets_cooldown_then_retries(test_db_session, monkeypatch):
    """A provider failure records the key; retries defer until cooldown ends."""

    def _exploding_generate(self, prompt, **kwargs) -> str:
        raise RuntimeError("provider down")

    class _ExplodingProvider:
        generate_sync = _exploding_generate

    autogen.set_llm_provider_factory(lambda: _ExplodingProvider())
    key = autogen._PendingKey("quasar", "es")

    started: list[threading.Thread] = []

    def capturing_start(self):
        # Run the thread target synchronously so failure recording is
        # deterministic and no background thread outlives the test.
        started.append(self)
        return self.run()

    with patch.object(
        threading.Thread, "start", new=capturing_start
    ):
        # First attempt: the provider blows up -> failure recorded. The real
        # thread runs once (synchronously through the capture wrapper).
        autogen.ensure_symbol_generated("quasar", "es")
    assert len(started) == 1
    assert autogen._in_flight == set()
    assert key in autogen._recent_failures

    # A second call within the cooldown must not spawn another attempt.
    with patch.object(threading.Thread, "start", new=capturing_start):
        autogen.ensure_symbol_generated("quasar", "es")
    assert len(started) == 1

    # After the cooldown elapses the word is retried once.
    with autogen._lock:
        autogen._recent_failures[key] = 0  # long ago
    with patch.object(threading.Thread, "start", new=capturing_start):
        autogen.ensure_symbol_generated("quasar", "es")
    assert len(started) == 2


def test_rate_limited_generation_retries_sooner_than_generic_failure(
    test_db_session, monkeypatch
):
    """A 429 records a short cooldown so the word retries well before the
    generic 5-minute failure cooldown would allow."""
    import time as time_module

    from src.aac_app.providers.base_provider import ProviderRateLimitError

    class _RateLimitedProvider:
        def generate_sync(self, prompt, **kwargs) -> str:
            raise ProviderRateLimitError("Groq rate limited (429)")

    autogen.set_llm_provider_factory(lambda: _RateLimitedProvider())
    key = autogen._PendingKey("quasar", "es")

    started: list[threading.Thread] = []

    def capturing_start(self):
        started.append(self)
        return self.run()

    with patch.object(threading.Thread, "start", new=capturing_start):
        autogen.ensure_symbol_generated("quasar", "es")
    assert len(started) == 1
    assert key in autogen._recent_failures
    assert key in autogen._rate_limited

    # 40s ago: inside the 5-min generic cooldown but past the 30s
    # rate-limit cooldown -> the word retries now.
    with autogen._lock:
        autogen._recent_failures[key] = time_module.monotonic() - 40
    with patch.object(threading.Thread, "start", new=capturing_start):
        autogen.ensure_symbol_generated("quasar", "es")
    assert len(started) == 2

    # The same age for a generic failure is still inside its cooldown.
    with autogen._lock:
        autogen._rate_limited.discard(key)
        autogen._recent_failures[key] = time_module.monotonic() - 40
    with patch.object(threading.Thread, "start", new=capturing_start):
        autogen.ensure_symbol_generated("quasar", "es")
    assert len(started) == 2  # unchanged: blocked until the 5-minute mark


def test_consecutive_generations_are_paced(test_db_session, monkeypatch):
    """Queued pictograms space their LLM calls so a burst of missing words
    does not trip the provider's per-minute quota (Groq 429s)."""
    import time as time_module

    monkeypatch.setattr(autogen, "_pacing_seconds", lambda: 0.2)
    call_times: list[float] = []

    class _PacedProvider:
        def generate_sync(self, prompt, **kwargs) -> str:
            call_times.append(time_module.monotonic())
            return '{"background":"#fff","shapes":[{"kind":"circle","cx":0,"cy":0,"r":10,"fill":"#FFD166"}]}'

    autogen.set_llm_provider_factory(lambda: _PacedProvider())
    with (
        patch.object(autogen, "_has_catalog_symbol", return_value=False),
        patch.object(autogen, "_count_generated_today", return_value=0),
        patch.object(autogen, "_persist_generated_symbol", return_value=None),
    ):
        for label in ("uno", "dos", "tres"):
            autogen._generate_in_background(
                autogen._PendingKey(label, "es"), label, "es"
            )

    assert len(call_times) == 3
    assert call_times[1] - call_times[0] >= 0.15
    assert call_times[2] - call_times[1] >= 0.15


def test_prediction_hook_schedules_generation_for_text_only_word(
    test_db_session, regular_user, monkeypatch
):
    """predict_next triggers background generation exactly for text-only words."""
    from unittest.mock import Mock

    from src.aac_app.services import prediction_service as ps_module
    from src.aac_app.services import symbol_svg_autogen as autogen_module

    service = ps_module.PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)
    test_db_session.add_all(
        [
            Symbol(label="vaca", category="farm_animals", language="es", is_builtin=True),
            Symbol(label="cow", category="farm_animals", language="en", is_builtin=True),
        ]
    )
    test_db_session.commit()

    scheduled: list[tuple[str, str]] = []
    fetched = Mock(return_value=["nebulosa", "supernova", "telescopio"])
    with patch.object(autogen_module, "autogen_enabled", return_value=True), patch.object(
        autogen_module,
        "ensure_symbol_generated",
        side_effect=lambda word, lang: scheduled.append((word, lang)),
    ):
        try:
            service.predict_next(
                user_id=regular_user.id,
                current_symbols=[],
                limit=6,
                language="es",
                offset=0,
                topic="astrofísica",
                topic_word_fetcher=fetched,
                db=test_db_session,
            )
        finally:
            ps_module._topics_word_cache.clear()

    assert scheduled == [("nebulosa", "es"), ("supernova", "es"), ("telescopio", "es")]


def test_text_only_suggestions_mark_is_generating_when_enabled(
    test_db_session, regular_user, monkeypatch
):
    """With autogen on, text-only words carry is_generating for the frontend."""
    from unittest.mock import Mock

    from src.aac_app.services import prediction_service as ps_module
    from src.aac_app.services import symbol_svg_autogen as autogen_module

    service = ps_module.PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)
    test_db_session.add_all(
        [
            Symbol(label="vaca", category="farm_animals", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()

    fetched = Mock(return_value=["nebulosa"])
    with patch.object(autogen_module, "autogen_enabled", return_value=True), patch.object(
        autogen_module, "ensure_symbol_generated", return_value=None
    ):
        try:
            suggestions = service.predict_next(
                user_id=regular_user.id,
                current_symbols=[],
                limit=4,
                language="es",
                offset=0,
                topic="astrofísica",
                topic_word_fetcher=fetched,
                db=test_db_session,
            )
        finally:
            ps_module._topics_word_cache.clear()

    ai = [s for s in suggestions if s.get("is_text_only")]
    assert ai and ai[0]["label"] == "nebulosa"
    assert ai[0]["is_generating"] is True


def test_daily_budget_stops_generation_when_cap_reached(test_db_session, monkeypatch):
    """Once the day's cap is used, no new generation is scheduled or run."""
    autogen.invalidate_generated_today_cache()
    monkeypatch.setattr(autogen, "_daily_cap", lambda: 2)

    # Two symbols already generated today -> budget exhausted.

    with patch.object(autogen, "_count_generated_today", return_value=2):
        assert autogen._daily_budget_remaining() == 0
        assert autogen.autogen_can_generate() is False

        # Fast path: nothing is spawned when the budget is gone.
        spawned: list[threading.Thread] = []

        def capturing_start(self):
            spawned.append(self)

        with patch.object(threading.Thread, "start", new=capturing_start):
            autogen.ensure_symbol_generated("nebulosa", "es")
        assert spawned == []

        # Hard stop at spend time even if a thread slipped through: the fresh
        # count already equals the cap, so the provider must not be called.
        calls = []
        key = autogen._PendingKey("quasar", "es")
        with patch.object(autogen, "_generate_sync_callable", side_effect=lambda: calls.append(1) or None), patch.object(
            autogen, "_has_catalog_symbol", return_value=False
        ):
            autogen._generate_in_background(key, "quasar", "es")
        assert calls == []

    # With budget remaining, generation proceeds.
    autogen.invalidate_generated_today_cache()
    calls2 = []

    class _FakeProvider:
        def generate_sync(self, prompt, **kwargs) -> str:
            calls2.append(1)
            return '{"background":"#fff","shapes":[{"kind":"circle","cx":0,"cy":0,"r":10,"fill":"#FFD166"}]}'

    autogen.set_llm_provider_factory(lambda: _FakeProvider())
    with patch.object(autogen, "_count_generated_today", return_value=1), patch(
        "src.aac_app.db.get_session",
        side_effect=lambda: test_db_session,
    ), patch.object(autogen, "_has_catalog_symbol", return_value=False):
        autogen._generate_in_background(
            autogen._PendingKey("galaxia", "es"), "galaxia", "es"
        )
    assert calls2 == [1]


def test_zero_cap_disables_autogen(test_db_session, monkeypatch):
    """A persisted cap of 0 disables auto-generation entirely."""
    autogen.invalidate_generated_today_cache()
    monkeypatch.setattr(autogen, "_daily_cap", lambda: 0)
    with patch.object(autogen, "_count_generated_today", return_value=0):
        assert autogen.autogen_can_generate() is False
        spawned: list[threading.Thread] = []
        with patch.object(threading.Thread, "start", new=lambda self: spawned.append(self)):
            autogen.ensure_symbol_generated("nebulosa", "es")
        assert spawned == []


def test_generation_lock_makes_cap_hard_under_concurrency(test_db_session, monkeypatch):
    """Concurrent background threads never exceed the cap: the check + LLM
    call + persist run under a lock, so the second thread sees the count the
    first one incremented."""
    autogen.invalidate_generated_today_cache()
    monkeypatch.setattr(autogen, "_daily_cap", lambda: 1)
    counts = iter([0, 1])  # first thread sees 0, second sees 1 (already spent)
    generated = []

    class _FakeProvider:
        def generate_sync(self, prompt, **kwargs) -> str:
            generated.append(1)
            return '{"background":"#fff","shapes":[{"kind":"circle","cx":0,"cy":0,"r":10,"fill":"#FFD166"}]}'

    autogen.set_llm_provider_factory(lambda: _FakeProvider())
    with patch.object(autogen, "_count_generated_today", side_effect=lambda: next(counts)), patch(
        "src.aac_app.db.get_session",
        side_effect=lambda: test_db_session,
    ), patch.object(autogen, "_has_catalog_symbol", return_value=False):
        autogen._generate_in_background(autogen._PendingKey("uno", "es"), "uno", "es")
        autogen._generate_in_background(autogen._PendingKey("dos", "es"), "dos", "es")
    # Only the first thread (count 0 < cap 1) reached the LLM.
    assert generated == [1]


def test_auto_generated_symbol_reused_across_future_conversations(
    test_db_session, regular_user, monkeypatch
):
    """A pictogram generated once is reused in later conversations: a future
    topic that surfaces the same word resolves it to the stored symbol (with
    image) instead of emitting a text-only tile or regenerating it."""
    from unittest.mock import Mock

    from src.aac_app.services import prediction_service as ps_module
    from src.aac_app.services import symbol_svg_autogen as autogen_module

    service = ps_module.PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)

    # Simulate a pictogram auto-generated in an earlier conversation: it has
    # the autogen description marker and a stored image, exactly like a real
    # background generation would leave behind.
    generated = Symbol(
        label="nebulosa",
        description=autogen_module._AUTOGEN_DESC_PREFIX + " for the missing symbol 'nebulosa'.",
        category="general",
        image_path="/uploads/symbols/nebulosa.png",
        keywords="nebulosa",
        language="es",
        is_builtin=False,
    )
    test_db_session.add_all(
        [
            generated,
            Symbol(label="vaca", category="farm_animals", language="es", is_builtin=True),
        ]
    )
    test_db_session.commit()

    # A NEW topic (different conversation) whose word list happens to include
    # the already-generated word.
    fetched = Mock(return_value=["nebulosa", "pulsar"])
    scheduled: list[str] = []
    with patch.object(autogen_module, "autogen_enabled", return_value=True), patch.object(
        autogen_module,
        "ensure_symbol_generated",
        side_effect=lambda word, lang: scheduled.append(word),
    ):
        try:
            suggestions = service.predict_next(
                user_id=regular_user.id,
                current_symbols=[],
                limit=6,
                language="es",
                offset=0,
                topic="nuevo tema cósmico",
                topic_word_fetcher=fetched,
                db=test_db_session,
            )
        finally:
            ps_module._topics_word_cache.clear()

    by_label = {s["label"]: s for s in suggestions}
    # "nebulosa" is reused: real symbol with the stored image, not text-only.
    reused = by_label.get("nebulosa")
    assert reused is not None
    assert reused["symbol_id"] == generated.id
    assert reused["image_path"] == "/uploads/symbols/nebulosa.png"
    assert reused.get("is_text_only") is not True
    # Only the truly-missing word gets scheduled for generation.
    assert scheduled == ["pulsar"]
