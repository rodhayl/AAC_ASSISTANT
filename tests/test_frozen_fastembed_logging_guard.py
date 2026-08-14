"""Regression coverage for frozen / windowed PyInstaller builds.

In ``console=False`` PyInstaller builds, ``sys.stdout`` and ``sys.stderr``
are ``None``. Libraries such as ``fastembed``, ``huggingface_hub``, and
``onnxruntime`` may attempt to write progress/status to stdout/stderr
during model construction; the ``.write()`` call raises ``AttributeError``
on a ``None`` stream and kills the background indexing task.  The vector
store builds its embedding model lazily and must survive the frozen /
windowed environment so that semantic search can still initialize in a
packaged build.
"""

from __future__ import annotations

import sys

import pytest


class PrintToStdoutEmbedder:
    """Simulate fastembed (or its deps) writing to stdout/stderr in __init__."""

    def __init__(self, *args, **kwargs):
        # Common fastembed/onnxruntime/huggingface_hub calls during init:
        sys.stdout.write("loading model...\n")
        sys.stderr.write("warming up...\n")


class FailingNetworkEmbedder:
    """Simulate a real model load that fails for unrelated reasons."""

    def __init__(self, *args, **kwargs):
        raise OSError("simulated network unavailable in windowed frozen mode")


def test_ensure_model_loaded_survives_none_streams(tmp_path, monkeypatch):
    """Inner stdout writes during init must not crash under frozen windowed mode."""
    from src.aac_app.services import local_vector_store

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    store = local_vector_store.LocalVectorStore(
        index_path=str(tmp_path / "store.index"),
        metadata_path=str(tmp_path / "store.json"),
        embedder_factory=PrintToStdoutEmbedder,
        lazy_load=True,
    )

    # With the guard in place, the inner stdout writes succeed against the
    # redirect buffer and the embedder is registered as loaded.
    assert store._ensure_model_loaded() is True
    assert isinstance(store.embedder, PrintToStdoutEmbedder)
    assert store._model_loaded is True


def test_ensure_model_loaded_handles_real_failure_under_none_streams(tmp_path, monkeypatch):
    """A genuine init failure must be logged cleanly, not raise AttributeError."""
    from src.aac_app.services import local_vector_store

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    store = local_vector_store.LocalVectorStore(
        index_path=str(tmp_path / "store.index"),
        metadata_path=str(tmp_path / "store.json"),
        embedder_factory=FailingNetworkEmbedder,
        lazy_load=True,
    )

    # The init failure is caught and reported, no AttributeError for NoneType.
    assert store._ensure_model_loaded() is False
    assert store.embedder is None
    assert store._model_loaded is True  # attempt was made


def test_normal_streams_are_restored_after_init(tmp_path):
    """A normal (non-frozen) run must keep the user's stdout/stderr intact."""
    from src.aac_app.services import local_vector_store

    real_out = sys.stdout
    real_err = sys.stderr
    # Sanity: pytest/capture leaves a real stream in place during normal runs.
    assert real_out is not None and real_err is not None

    store = local_vector_store.LocalVectorStore(
        index_path=str(tmp_path / "store.index"),
        metadata_path=str(tmp_path / "store.json"),
        embedder_factory=PrintToStdoutEmbedder,
        lazy_load=True,
    )

    assert store._ensure_model_loaded() is True
    # Original streams are preserved.
    assert sys.stdout is real_out
    assert sys.stderr is real_err


def test_index_all_symbols_survives_none_streams(tmp_path, monkeypatch):
    """The background indexing path used by lifespan must not crash with None streams."""
    from src.aac_app.services import local_vector_store

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    # Real init path uses an embedder_factory that writes to stdout during
    # init; with None streams this must succeed because safe_streams wraps
    # the call.  No network access is performed by PrintToStdoutEmbedder.
    store = local_vector_store.LocalVectorStore(
        index_path=str(tmp_path / "store.index"),
        metadata_path=str(tmp_path / "store.json"),
        embedder_factory=PrintToStdoutEmbedder,
        lazy_load=True,
    )
    assert store._ensure_model_loaded() is True


def test_speech_provider_load_survives_none_streams(tmp_path, monkeypatch):
    """The live faster-whisper load path is guarded against None stdio."""
    import importlib.util
    import types

    from src.aac_app.providers import local_speech_provider

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    class FakeWhisperModel:
        def __init__(self, *args, **kwargs):
            # Mimic faster_whisper/onnxruntime touching stdout in __init__.
            sys.stdout.write("download progress\n")
            sys.stderr.write("decoding progress\n")

    # Inject a fake faster_whisper module so the lazy import inside the
    # provider resolves without loading the real optional dependency. The
    # module-level ``faster_whisper`` cache is also restored so later tests
    # that transcribe real audio do not observe the fake.
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeWhisperModel
    fake.__spec__ = importlib.util.spec_from_loader("faster_whisper", loader=None)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(local_speech_provider, "faster_whisper", None)
    # The CI environment does not install the optional voice extra, so the
    # module-level availability flag is False at import time. Force the live
    # load path so the test exercises the None-stdio guard regardless of
    # whether the real faster-whisper stack is present.
    monkeypatch.setattr(local_speech_provider, "FASTER_WHISPER_AVAILABLE", True)

    provider = local_speech_provider.LocalSpeechProvider(
        model_size="tiny", model_cache_dir=str(tmp_path / "models")
    )
    provider._load_model()
    assert provider._model_loaded is True
    assert isinstance(provider.model, FakeWhisperModel)


def test_safe_streams_restores_outer_state():
    """The shared safe_streams helper must restore the original streams."""
    from src.aac_app.utils.runtime import safe_streams

    real_out, real_err = sys.stdout, sys.stderr
    with safe_streams():
        assert sys.stdout is real_out
        assert sys.stderr is real_err
    assert sys.stdout is real_out
    assert sys.stderr is real_err

    monkey = pytest.MonkeyPatch()
    monkey.setattr(sys, "stdout", None)
    monkey.setattr(sys, "stderr", None)
    try:
        with safe_streams():
            assert sys.stdout is not None
            assert sys.stderr is not None
        assert sys.stdout is None
        assert sys.stderr is None
    finally:
        monkey.undo()

