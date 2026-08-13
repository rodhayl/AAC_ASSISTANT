"""Regression coverage for the frozen launcher error-reporting path."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def _load_launcher():
    spec = importlib.util.spec_from_file_location("aac_launcher", REPO_ROOT / "launcher.pyw")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_startup_error_writes_to_first_available_candidate(tmp_path):
    launcher = _load_launcher()
    first = tmp_path / "first" / "logs"
    second = tmp_path / "second" / "logs"
    launcher._startup_log_directories = lambda: [first, second]

    launcher._write_startup_error("startup failed")

    assert (first / "startup_error.log").read_text(encoding="utf-8") == "startup failed"
    assert not (second / "startup_error.log").exists()


def test_startup_error_falls_back_after_permission_error(monkeypatch, tmp_path):
    launcher = _load_launcher()
    blocked = tmp_path / "blocked" / "logs"
    fallback = tmp_path / "fallback" / "logs"
    launcher._startup_log_directories = lambda: [blocked, fallback]

    original_mkdir = Path.mkdir

    def fail_blocked(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("read-only install directory")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_blocked)
    launcher._write_startup_error("original startup failure")

    assert (fallback / "startup_error.log").read_text(encoding="utf-8") == (
        "original startup failure"
    )


def test_startup_error_never_raises_when_all_candidates_are_unwritable(monkeypatch, tmp_path):
    launcher = _load_launcher()
    candidates = [tmp_path / "one", tmp_path / "two"]
    launcher._startup_log_directories = lambda: candidates

    def always_fail(*args, **kwargs):
        raise OSError("filesystem unavailable")

    monkeypatch.setattr(Path, "mkdir", always_fail)

    launcher._write_startup_error("preserve this diagnostic")
