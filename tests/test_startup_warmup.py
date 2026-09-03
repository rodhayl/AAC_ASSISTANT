"""Regression tests for startup warmup off critical path (VAL-OPS-021).

Tests:
1. ASGI-level: server serves / and /api/health within seconds even when
   warmup takes 30s; /ready returns 503 then 200.
2. Warmup timeout: a stuck worker does not block past the timeout; a
   completed future is never falsely reported as timed out.
3. Fix C: empty library skips model download in index_all_symbols.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

FRONTEND_INDEX = Path("src/frontend/dist/index.html")


def _frontend_is_built() -> bool:
    """True when a production SPA is available to serve.

    The CI backend job runs pytest on a fresh checkout with no built
    frontend, so SPA-serving assertions must be conditional there.
    """
    return FRONTEND_INDEX.is_file()

# ---------------------------------------------------------------------------
# Fix A — warmup off the critical path
# ---------------------------------------------------------------------------

class TestStartupServesDuringWarmup:
    """Warmup runs in background; server binds and serves immediately."""

    @pytest.fixture(autouse=True)
    def _reset_providers(self):
        from src.api.deps import reset_providers

        reset_providers()
        yield
        reset_providers()

    def test_health_and_spa_available_during_warmup(self, monkeypatch):
        """GET /api/health and GET / respond 200 within seconds of startup
        even when warmup_providers takes 30s; /ready returns 503 then 200."""
        from src.api.deps.providers import _startup_lock, _startup_state
        from src.api.main import app

        warmup_done = threading.Event()

        def slow_warmup(timeout_seconds: float = 30.0):
            """Simulate a long warmup that eventually succeeds."""
            warmup_done.wait(timeout=30)
            with _startup_lock:
                _startup_state["initialized"] = True
                _startup_state["initializing"] = False
                _startup_state["providers_ready"] = {
                    "speech": True,
                    "llm": True,
                    "achievement": True,
                    "vector_store": True,
                }
                _startup_state["startup_time_ms"] = 1000.0

        monkeypatch.setattr("src.api.main.warmup_providers", slow_warmup)
        monkeypatch.setattr("src.api.main.index_all_symbols", lambda *a, **kw: None)

        with TestClient(app) as client:
            # Server should be available immediately, not after 30s
            health = client.get("/api/health")
            assert health.status_code == 200

            spa = client.get("/")
            if _frontend_is_built():
                assert spa.status_code == 200

            ready = client.get("/ready")
            assert ready.status_code == 503
            assert ready.json()["status"] == "warming_up"

            # Let warmup complete
            warmup_done.set()
            time.sleep(0.5)

            ready = client.get("/ready")
            assert ready.status_code == 200

    def test_warmup_exception_does_not_block_startup(self, monkeypatch):
        """Even if warmup raises, the server starts and /api/health works."""
        from src.api.main import app

        def failing_warmup(timeout_seconds: float = 30.0):
            raise RuntimeError("warmup exploded")

        monkeypatch.setattr("src.api.main.warmup_providers", failing_warmup)
        monkeypatch.setattr("src.api.main.index_all_symbols", lambda *a, **kw: None)

        with TestClient(app) as client:
            health = client.get("/api/health")
            assert health.status_code == 200

    def test_database_startup_failure_blocks_readiness_but_not_liveness(self, monkeypatch):
        """A failed schema/seed step must never advertise a ready service."""
        from src.api.main import app

        monkeypatch.setattr("src.api.main.schema.ensure", lambda: None)
        monkeypatch.setattr(
            "src.api.main.init_database",
            lambda ensure_schema=False: (_ for _ in ()).throw(
                RuntimeError("database unavailable")
            ),
        )
        monkeypatch.setattr("src.api.main.warmup_providers", lambda timeout_seconds=30.0: None)
        monkeypatch.setattr(
            "src.api.main.index_all_symbols",
            lambda *a, **kw: (_ for _ in ()).throw(
                AssertionError("indexing must be skipped when database initialization fails")
            ),
        )

        with TestClient(app) as client:
            assert client.get("/api/health").status_code == 200
            ready = client.get("/ready")
            assert ready.status_code == 503
            assert ready.json()["status"] == "database_unavailable"

    def test_ready_reports_degraded_when_a_provider_failed(self, monkeypatch):
        """Warmup completing with a failed provider yields 503 degraded, not healthy."""
        from src.api.deps.providers import _startup_lock, _startup_state
        from src.api.main import app

        def degraded_warmup(timeout_seconds: float = 30.0):
            with _startup_lock:
                _startup_state["initialized"] = True
                _startup_state["initializing"] = False
                _startup_state["providers_ready"] = {
                    "speech": True,
                    "llm": False,  # Groq unavailable: the only production LLM
                    "achievement": True,
                    "vector_store": True,
                }
                _startup_state["errors"] = ["llm: Groq API key missing"]
                _startup_state["startup_time_ms"] = 2500.0

        monkeypatch.setattr("src.api.main.warmup_providers", degraded_warmup)
        monkeypatch.setattr("src.api.main.index_all_symbols", lambda *a, **kw: None)

        with TestClient(app) as client:
            ready = client.get("/ready")
            assert ready.status_code == 503
            data = ready.json()
            assert data["status"] == "degraded"
            assert data["ready"] is False
            assert data["providers"]["llm"] is False
            assert "Groq API key missing" in data["errors"][0]



# ---------------------------------------------------------------------------
# Fix B — warmup_providers timeout and shutdown correctness
# ---------------------------------------------------------------------------

class TestLifespanShutdown:
    """Startup task wrappers are drained when the ASGI lifespan exits."""

    def test_background_startup_tasks_are_cancelled_on_shutdown(self, monkeypatch):
        from src.api.main import app, lifespan

        started_names: set[str] = set()
        cancelled: list[str] = []

        async def blocking_to_thread(func, *_args, **_kwargs):
            started_names.add(getattr(func, "__name__", "unknown"))
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(getattr(func, "__name__", "unknown"))
                raise

        monkeypatch.setattr("src.api.main.schema.ensure", lambda: None)
        monkeypatch.setattr("src.api.main.init_database", lambda ensure_schema=False: None)
        monkeypatch.setattr("src.api.main.asyncio.to_thread", blocking_to_thread)

        async def exercise_lifespan():
            async with lifespan(app):
                deadline = asyncio.get_running_loop().time() + 1
                while started_names != {"warmup_providers", "run_index"}:
                    if asyncio.get_running_loop().time() >= deadline:
                        raise AssertionError(f"Started tasks: {started_names}")
                    await asyncio.sleep(0.01)

        asyncio.run(exercise_lifespan())

        assert set(cancelled) == {"warmup_providers", "run_index"}

    def test_index_timeout_defers_vector_close_but_runs_provider_cleanup(self, monkeypatch):
        """A stuck native index cannot suppress non-vector provider cleanup."""
        from src.api.main import app, lifespan

        index_started = threading.Event()
        release_index = threading.Event()
        cleanup_calls: list[dict] = []

        monkeypatch.setattr("src.api.main.schema.ensure", lambda: None)
        monkeypatch.setattr("src.api.main.init_database", lambda ensure_schema=False: None)
        monkeypatch.setattr("src.api.main.warmup_providers", lambda timeout_seconds=30.0: None)
        monkeypatch.setattr(
            "src.api.main.config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", 3
        )

        def hanging_index():
            index_started.set()
            release_index.wait(timeout=5)

        async def fake_reset_providers_async(**kwargs):
            cleanup_calls.append(kwargs)

        monkeypatch.setattr("src.api.main.index_all_symbols", hanging_index)
        monkeypatch.setattr("src.api.main.reset_providers_async", fake_reset_providers_async)

        async def exercise_lifespan():
            async with lifespan(app):
                deadline = asyncio.get_running_loop().time() + 1
                while not index_started.is_set():
                    if asyncio.get_running_loop().time() >= deadline:
                        raise AssertionError("index worker did not start")
                    await asyncio.sleep(0.01)

        asyncio.run(exercise_lifespan())
        release_index.set()

        assert cleanup_calls
        assert cleanup_calls[0]["close_vector_store"] is False
        assert cleanup_calls[0]["timeout_seconds"] > 0
        assert cleanup_calls[0]["timeout_seconds"] < 3

    @pytest.mark.parametrize("configured_timeout", [1, 2, 3])
    def test_shutdown_budget_always_leaves_uvicorn_handoff_buffer(
        self, monkeypatch, configured_timeout
    ):
        from src.api.main import app, lifespan

        cleanup_calls: list[dict] = []
        monkeypatch.setattr("src.api.main.schema.ensure", lambda: None)
        monkeypatch.setattr("src.api.main.init_database", lambda ensure_schema=False: None)
        monkeypatch.setattr("src.api.main.warmup_providers", lambda timeout_seconds=30.0: None)
        monkeypatch.setattr(
            "src.api.main.config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS",
            configured_timeout,
        )
        monkeypatch.setattr("src.api.main.index_all_symbols", lambda: None)

        async def fake_reset_providers_async(**kwargs):
            cleanup_calls.append(kwargs)

        monkeypatch.setattr("src.api.main.reset_providers_async", fake_reset_providers_async)

        async def exercise_lifespan():
            async with lifespan(app):
                await asyncio.sleep(0.01)

        asyncio.run(exercise_lifespan())

        assert cleanup_calls
        budget = cleanup_calls[0]["timeout_seconds"]
        assert 0 < budget < configured_timeout


class TestWarmupTimeoutCorrectness:
    """warmup_providers timeout and shutdown correctness."""

    @pytest.fixture(autouse=True)
    def _reset_providers(self):
        from src.api.deps import reset_providers

        reset_providers()
        yield
        reset_providers()

    def test_stuck_worker_does_not_block_past_timeout(self, monkeypatch):
        """A stuck worker cannot hold warmup past the timeout.

        With the old ``with ThreadPoolExecutor`` pattern, ``__exit__`` calls
        ``shutdown(wait=True)`` which blocks until the stuck thread finishes.
        The fix uses ``shutdown(wait=False, cancel_futures=True)`` in a
        ``finally`` so the executor never waits for a stuck worker.
        """
        from src.api.deps import providers as providers_mod
        from src.api.deps import warmup_providers

        block = threading.Event()

        def stuck_init():
            block.wait(timeout=3)
            return True

        monkeypatch.setattr(providers_mod, "_init_speech_provider_sync", stuck_init)
        monkeypatch.setattr(providers_mod, "_init_llm_provider_sync", lambda: True)
        monkeypatch.setattr(providers_mod, "_init_achievement_system_sync", lambda: True)
        monkeypatch.setattr(providers_mod, "_init_vector_store_sync", lambda: True)

        start = time.time()
        state = warmup_providers(timeout_seconds=1.0)
        elapsed = time.time() - start

        block.set()  # release the stuck thread for cleanup

        assert elapsed < 2.5, f"Warmup took {elapsed:.1f}s; stuck worker blocked exit"
        assert state["initialized"] is True
        assert state["providers_ready"]["speech"] is False

    def test_completed_future_not_reported_as_timed_out(self, monkeypatch):
        """A completed future is never falsely reported as timed out.

        One slow provider (speech) exceeds the timeout.  The other three
        complete instantly.  By the time the loop checks them, the overall
        timeout has been exceeded (``remaining_time <= 0``) but the futures
        are already done.  The old code blindly raises ``FutureTimeoutError``
        for every remaining future; the fix checks ``future.done()`` first.
        """
        from src.api.deps import providers as providers_mod
        from src.api.deps import warmup_providers

        def slow_speech():
            time.sleep(0.5)
            return True

        monkeypatch.setattr(providers_mod, "_init_speech_provider_sync", slow_speech)
        monkeypatch.setattr(providers_mod, "_init_llm_provider_sync", lambda: True)
        monkeypatch.setattr(providers_mod, "_init_achievement_system_sync", lambda: True)
        monkeypatch.setattr(providers_mod, "_init_vector_store_sync", lambda: True)

        state = warmup_providers(timeout_seconds=0.2)

        # speech genuinely timed out
        assert state["providers_ready"]["speech"] is False

        # The other three completed successfully — they must NOT be
        # reported as timed out.
        assert state["providers_ready"]["llm"] is True, (
            "llm completed but was falsely reported as timed out"
        )
        assert state["providers_ready"]["achievement"] is True, (
            "achievement completed but was falsely reported as timed out"
        )
        assert state["providers_ready"]["vector_store"] is True, (
            "vector_store completed but was falsely reported as timed out"
        )

        timeout_errors = [e for e in state["errors"] if "timed out" in e]
        assert len(timeout_errors) == 1, f"Expected 1 timeout (speech), got: {timeout_errors}"
        assert "speech" in timeout_errors[0]


# ---------------------------------------------------------------------------
# Fix C — empty library skips model download
# ---------------------------------------------------------------------------

class TestIndexAllSymbolsEmptyLibrary:
    """Empty library skips model download in index_all_symbols."""

    def test_empty_library_skips_model_load(self, monkeypatch):
        """If the symbols query is empty, mark_indexed() and return BEFORE
        load_index_if_available() to skip pointless model-download attempts."""
        from src.aac_app.services import vector_utils

        mark_called = []

        class EmptyLibraryStore:
            model = None
            metadata = []

            def has_persisted_metadata(self):
                return False

            def is_available(self):
                return True

            def load_index_if_available(self):
                raise AssertionError(
                    "model load should be skipped on empty library"
                )

            def mark_indexed(self):
                mark_called.append(True)

            def add_texts(self, texts, metadatas):
                raise AssertionError("should not add texts for empty library")

        store = EmptyLibraryStore()
        monkeypatch.setattr(vector_utils, "get_vector_store", lambda: store)

        @contextmanager
        def mock_get_session():
            # Mirror the real SQLAlchemy Query API: every clause returns the
            # query itself so production needs no test-double fallbacks.
            mock_db = Mock()
            query = mock_db.query.return_value
            query.order_by.return_value = query
            query.yield_per.return_value = query
            query.first.return_value = None
            yield mock_db

        monkeypatch.setattr(vector_utils, "get_session", mock_get_session)

        vector_utils.index_all_symbols()

        assert mark_called, "mark_indexed() should be called for empty library"
