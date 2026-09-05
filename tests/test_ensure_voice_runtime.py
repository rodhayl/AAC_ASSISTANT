"""Regression tests for the voice-runtime preparation CLI."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ensure_voice_runtime.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("ensure_voice_runtime_test_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_help_is_fast_and_does_not_import_voice_modules():
    """--help exits before optional voice imports or filesystem preparation."""
    code = """
import builtins
import runpy
import sys

real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name.startswith("src.aac_app.providers.local_"):
        raise AssertionError(f"voice module imported during --help: {name}")
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
sys.argv = ["ensure_voice_runtime.py", "--help"]
try:
    runpy.run_path("scripts/ensure_voice_runtime.py", run_name="__main__")
except SystemExit as exc:
    raise SystemExit(exc.code)
"""
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr or result.stdout
    assert "usage:" in result.stdout
    assert "Voice runtime ready" not in result.stdout
    assert elapsed < 2.0


def test_check_mode_never_downloads_when_model_files_are_missing(monkeypatch):
    """--check reports missing files instead of invoking the downloader."""
    module = _load_script_module()
    downloaded = False
    fake_speech = ModuleType("src.aac_app.providers.local_speech_provider")
    fake_speech.is_faster_whisper_available = lambda: True
    fake_tts = ModuleType("src.aac_app.providers.local_tts_provider")
    fake_tts.get_local_tts_provider = lambda: SimpleNamespace(is_installed=lambda: True)
    fake_tts.model_files_present = lambda: False

    def fail_download():
        nonlocal downloaded
        downloaded = True
        raise AssertionError("--check attempted a model download")

    fake_tts.download_kokoro_model = fail_download
    monkeypatch.setitem(sys.modules, "src.aac_app.providers.local_speech_provider", fake_speech)
    monkeypatch.setitem(sys.modules, "src.aac_app.providers.local_tts_provider", fake_tts)

    assert module.main(["--check"]) == 1
    assert downloaded is False


def test_no_argument_path_still_prepares_missing_model(monkeypatch, capsys):
    """The launcher-compatible no-argument path still downloads missing files."""
    module = _load_script_module()
    calls: list[str] = []
    fake_speech = ModuleType("src.aac_app.providers.local_speech_provider")
    fake_speech.is_faster_whisper_available = lambda: True
    fake_tts = ModuleType("src.aac_app.providers.local_tts_provider")
    fake_tts.get_local_tts_provider = lambda: SimpleNamespace(is_installed=lambda: True)
    fake_tts.model_files_present = lambda: False

    def download():
        calls.append("download")
        return True

    fake_tts.download_kokoro_model = download
    monkeypatch.setitem(sys.modules, "src.aac_app.providers.local_speech_provider", fake_speech)
    monkeypatch.setitem(sys.modules, "src.aac_app.providers.local_tts_provider", fake_tts)

    assert module.main([]) == 0
    assert calls == ["download"]
    assert "Voice runtime ready" in capsys.readouterr().out
