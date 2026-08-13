"""Regression tests for bundled-model cache resolution.

`resolve_model_cache_dir` decides whether the optional AI models (fastembed and
faster-whisper) load from the read-only release bundle with ``local_files_only``
or fall back to the writable ``data/models`` directory with on-demand download.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config


@pytest.fixture
def no_bundled_models(monkeypatch):
    monkeypatch.setattr(config, "get_bundled_models_dir", lambda: None)


def test_resolve_returns_bundled_dir_and_local_only_when_model_present(
    tmp_path: Path, monkeypatch
):
    bundled = tmp_path / "bundled"
    (bundled / "models--Systran--faster-whisper-tiny").mkdir(parents=True)
    monkeypatch.setattr(config, "get_bundled_models_dir", lambda: bundled)

    cache_dir, local_files_only = config.resolve_model_cache_dir(
        "models--Systran--faster-whisper-tiny"
    )

    assert cache_dir == bundled
    assert local_files_only is True


def test_resolve_falls_back_to_writable_dir_for_other_model_size(
    tmp_path: Path, monkeypatch
):
    bundled = tmp_path / "bundled"
    (bundled / "models--Systran--faster-whisper-tiny").mkdir(parents=True)
    monkeypatch.setattr(config, "get_bundled_models_dir", lambda: bundled)
    monkeypatch.setattr(config, "get_data_path", lambda rel="": tmp_path / "data" / rel)

    cache_dir, local_files_only = config.resolve_model_cache_dir(
        "models--Systran--faster-whisper-base"
    )

    assert cache_dir == tmp_path / "data" / "models"
    assert local_files_only is False


def test_resolve_falls_back_to_writable_dir_when_no_bundle(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "get_bundled_models_dir", lambda: None)
    monkeypatch.setattr(config, "get_data_path", lambda rel="": tmp_path / "data" / rel)

    cache_dir, local_files_only = config.resolve_model_cache_dir(
        "models--qdrant--all-MiniLM-L6-v2-onnx"
    )

    assert cache_dir == tmp_path / "data" / "models"
    assert local_files_only is False


def test_resolve_prefers_specific_model_not_any_bundled_dir(tmp_path: Path, monkeypatch):
    # Only the fastembed model is bundled; a whisper request must not treat it as
    # a local-only hit.
    bundled = tmp_path / "bundled"
    (bundled / "models--qdrant--all-MiniLM-L6-v2-onnx").mkdir(parents=True)
    monkeypatch.setattr(config, "get_bundled_models_dir", lambda: bundled)
    monkeypatch.setattr(config, "get_data_path", lambda rel="": tmp_path / "data" / rel)

    cache_dir, local_files_only = config.resolve_model_cache_dir(
        "models--Systran--faster-whisper-tiny"
    )

    assert cache_dir == tmp_path / "data" / "models"
    assert local_files_only is False
