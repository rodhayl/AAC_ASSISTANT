from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest


def test_warmup_records_provider_metrics(monkeypatch):
    from src.api.deps import providers

    providers.reset_providers()
    monkeypatch.setattr(providers, "_init_speech_provider_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_llm_provider_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_achievement_system_sync", lambda: False)
    monkeypatch.setattr(providers, "_init_vector_store_sync", lambda: True)

    state = providers.warmup_providers(timeout_seconds=2)

    assert set(state["provider_metrics"]) == {
        "speech",
        "llm",
        "achievement",
        "vector_store",
    }
    assert state["provider_metrics"]["speech"]["success"] is True
    assert state["provider_metrics"]["achievement"]["success"] is False
    assert all(
        metric["duration_ms"] is None or metric["duration_ms"] >= 0
        for metric in state["provider_metrics"].values()
    )
    assert all(metric["timed_out"] is False for metric in state["provider_metrics"].values())

    providers.reset_providers()


def test_warmup_marks_timeout_metrics_explicitly(monkeypatch):
    from src.api.deps import providers

    providers.reset_providers()

    def stuck_initializer():
        import time

        time.sleep(0.2)
        return True

    monkeypatch.setattr(providers, "_init_speech_provider_sync", stuck_initializer)
    monkeypatch.setattr(providers, "_init_llm_provider_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_achievement_system_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_vector_store_sync", lambda: True)

    state = providers.warmup_providers(timeout_seconds=0.01)

    speech_metric = state["provider_metrics"]["speech"]
    assert speech_metric == {
        "success": False,
        "duration_ms": None,
        "timed_out": True,
    }
    assert state["errors"] == ["speech initialization timed out"]
    providers.reset_providers()

    providers.reset_providers()


def test_warmup_returns_defensive_snapshot(monkeypatch):
    from src.api.deps import providers

    providers.reset_providers()
    monkeypatch.setattr(providers, "_init_speech_provider_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_llm_provider_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_achievement_system_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_vector_store_sync", lambda: True)

    state = providers.warmup_providers(timeout_seconds=2)
    state["providers_ready"]["speech"] = False
    state["provider_metrics"]["speech"]["success"] = False

    snapshot = providers.get_startup_state()
    assert snapshot["providers_ready"]["speech"] is True
    assert snapshot["provider_metrics"]["speech"]["success"] is True
    providers.reset_providers()


def test_reset_discards_inflight_warmup_generation(monkeypatch):
    from src.api.deps import providers

    providers.reset_providers()
    release = threading.Event()
    started = threading.Event()

    def blocked_speech():
        started.set()
        release.wait(timeout=2)
        return True

    monkeypatch.setattr(providers, "_init_speech_provider_sync", blocked_speech)
    monkeypatch.setattr(providers, "_init_llm_provider_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_achievement_system_sync", lambda: True)
    monkeypatch.setattr(providers, "_init_vector_store_sync", lambda: True)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(providers.warmup_providers, 1)
        assert started.wait(timeout=1)
        providers.reset_providers()
        release.set()
        future.result(timeout=2)

    assert providers.get_startup_state()["initialized"] is False
    providers.reset_providers()


def test_lmstudio_provider_first_initialization_returns_instance(monkeypatch):
    from src.api.deps import providers

    providers.reset_providers()
    monkeypatch.setattr(
        providers,
        "_get_setting_value",
        lambda key, default="": {
            "lmstudio_base_url": "http://localhost:1234/v1",
            "lmstudio_model": "test-model",
        }.get(key, default),
    )

    provider = providers.get_lmstudio_provider()

    assert provider.base_url == "http://localhost:1234/v1"
    assert provider.default_model == "test-model"
    providers.reset_providers()


def test_reset_speech_provider_release_failure_is_non_fatal(monkeypatch):
    from src.api.deps import providers

    def fail_release():
        raise RuntimeError("release failed")

    monkeypatch.setattr(
        providers,
        "_speech_provider",
        SimpleNamespace(model_size="tiny", release=fail_release),
    )
    providers.reset_speech_provider()
    assert providers._speech_provider is None


def test_provider_getter_and_reset_are_safe_under_concurrency(monkeypatch):
    from src.api.deps import providers

    providers.reset_providers()
    monkeypatch.setattr(providers, "_get_setting_value", lambda key, default="": "tiny")
    created: list[object] = []
    created_lock = threading.Lock()

    class FakeSpeechProvider:
        model_size = "tiny"

        def __init__(self, **_kwargs):
            with created_lock:
                created.append(self)

    monkeypatch.setattr(providers, "LocalSpeechProvider", FakeSpeechProvider)

    def get_or_reset(index: int):
        if index % 2:
            providers.reset_speech_provider()
            return None
        return providers.get_speech_provider()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(get_or_reset, range(40)))

    assert all(result is None or result.model_size == "tiny" for result in results)
    assert created
    providers.reset_providers()


def test_reset_providers_closes_vector_store_without_disposing_shared_engine(monkeypatch):
    from src.api.deps import providers

    closed: list[bool] = []
    store = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(providers, "_vector_store", store)

    providers.reset_providers()

    assert closed == [True]
    assert providers._vector_store is None


def test_reset_speech_provider_releases_discarded_instance(monkeypatch):
    from src.api.deps import providers

    released: list[bool] = []
    fake = SimpleNamespace(model_size="tiny", release=lambda: released.append(True))
    monkeypatch.setattr(providers, "_speech_provider", fake)

    providers.reset_speech_provider()

    assert released == [True]
    assert providers._speech_provider is None


def test_ollama_getter_reuses_provider_when_model_setting_is_empty(monkeypatch):
    """An unset model must not recreate HTTP clients on every dependency call."""
    from src.api.deps import providers

    providers.reset_providers()
    created: list[object] = []
    closed: list[object] = []

    class FakeOllamaProvider:
        def __init__(self, *, base_url, model):
            self.base_url = base_url
            self._configured_model = model or ""
            self.recommended_model = "qwen:7b-q4_0"
            created.append(self)

        def close_sync(self):
            closed.append(self)

    monkeypatch.setattr(providers, "OllamaProvider", FakeOllamaProvider)
    monkeypatch.setattr(
        providers,
        "_get_setting_value",
        lambda key, default="": {
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "",
        }.get(key, default),
    )

    first = providers.get_ollama_provider()
    second = providers.get_ollama_provider()

    assert first is second
    assert len(created) == 1
    assert closed == []

    providers.reset_providers()
    assert closed == [first]


@pytest.mark.anyio
async def test_async_reset_reports_and_drains_timed_out_speech_release(monkeypatch):
    from src.api.deps import providers

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class HangingSpeech:
        def release(self):
            started.set()
            release.wait(timeout=2)
            finished.set()

    monkeypatch.setattr(providers, "_speech_provider", HangingSpeech())
    monkeypatch.setattr(providers.config, "BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", 0.05)

    await providers.reset_providers_async()

    assert started.is_set()
    with providers._speech_release_lock:
        assert providers._speech_release_workers

    release.set()
    deadline = asyncio.get_running_loop().time() + 1
    while not finished.is_set() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
    assert finished.is_set()
    for _ in range(20):
        with providers._speech_release_lock:
            if not providers._speech_release_workers:
                break
        await asyncio.sleep(0.01)
    with providers._speech_release_lock:
        assert not providers._speech_release_workers


@pytest.mark.anyio
async def test_reset_providers_async_awaits_provider_close(monkeypatch):
    from src.api.deps import providers

    closed: list[str] = []

    class AsyncOnlyProvider:
        async def close(self):
            closed.append("async")

    monkeypatch.setattr(providers, "_ollama_provider", AsyncOnlyProvider())
    monkeypatch.setattr(providers, "_openrouter_provider", None)
    monkeypatch.setattr(providers, "_lmstudio_provider", None)
    monkeypatch.setattr(providers, "_speech_provider", None)

    await providers.reset_providers_async()

    assert closed == ["async"]


@pytest.mark.anyio
async def test_async_reset_continues_after_provider_close_failure(monkeypatch):
    from src.api.deps import providers

    closed: list[str] = []

    class FailingProvider:
        async def close(self):
            raise RuntimeError("close failed")

    class HealthyProvider:
        async def close(self):
            closed.append("healthy")

    monkeypatch.setattr(providers, "_ollama_provider", FailingProvider())
    monkeypatch.setattr(providers, "_openrouter_provider", HealthyProvider())
    monkeypatch.setattr(providers, "_lmstudio_provider", None)
    monkeypatch.setattr(providers, "_speech_provider", None)

    await providers.reset_providers_async()

    assert closed == ["healthy"]


@pytest.mark.anyio
async def test_async_reset_bounds_hanging_provider_close(monkeypatch):
    from src.api.deps import providers

    class HangingProvider:
        async def close(self):
            import asyncio

            await asyncio.sleep(10)

    monkeypatch.setattr(providers, "_ollama_provider", HangingProvider())
    monkeypatch.setattr(providers, "_openrouter_provider", None)
    monkeypatch.setattr(providers, "_lmstudio_provider", None)
    monkeypatch.setattr(providers, "_speech_provider", None)
    monkeypatch.setattr(providers.config, "BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", 0.01)

    await providers.reset_providers_async()
    assert providers._ollama_provider is None


def test_reset_llm_providers_closes_all_cached_clients(monkeypatch):
    from src.api.deps import providers

    closed: list[str] = []

    def make_provider(name: str):
        return SimpleNamespace(close_sync=lambda: closed.append(name))

    monkeypatch.setattr(providers, "_ollama_provider", make_provider("ollama"))
    monkeypatch.setattr(providers, "_openrouter_provider", make_provider("openrouter"))
    monkeypatch.setattr(providers, "_lmstudio_provider", make_provider("lmstudio"))

    providers.reset_llm_providers()

    assert closed == ["ollama", "openrouter", "lmstudio"]
    assert providers._ollama_provider is None
    assert providers._openrouter_provider is None
    assert providers._lmstudio_provider is None


def test_stale_speech_warmup_releases_discarded_provider(monkeypatch):
    from src.api.deps import providers

    released: list[bool] = []

    class FakeSpeechProvider:
        def __init__(self, **_kwargs):
            self.release = lambda: released.append(True)

        def is_available(self):
            return True

    monkeypatch.setattr(providers, "LocalSpeechProvider", FakeSpeechProvider)
    monkeypatch.setattr(providers, "_startup_generation", 2)
    providers._warmup_generation_local.generation = 1

    try:
        assert providers._init_speech_provider_sync() is False
    finally:
        del providers._warmup_generation_local.generation

    assert released == [True]


def test_warmup_openrouter_passes_configured_model(monkeypatch):
    from src.api.deps import providers

    captured: dict[str, str] = {}

    class FakeOpenRouter:
        def __init__(self, *, api_key, model=None):
            captured.update(api_key=api_key, model=model or "")

    monkeypatch.setattr(providers, "OpenRouterProvider", FakeOpenRouter)
    monkeypatch.setattr(
        providers,
        "_get_setting_value",
        lambda key, default="": {
            "ai_provider": "openrouter",
            "openrouter_api_key": "key",
            "openrouter_model": "model-x",
        }.get(key, default),
    )
    providers.reset_providers()

    assert providers._init_llm_provider_sync() is True
    assert captured == {"api_key": "key", "model": "model-x"}
    providers.reset_providers()
