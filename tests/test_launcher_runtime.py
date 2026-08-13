"""Regression coverage for the frozen launcher error-reporting path."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def _load_launcher():
    """Load the Windows .pyw entry point consistently on every host OS."""
    launcher_path = REPO_ROOT / "launcher.pyw"
    loader = SourceFileLoader("aac_launcher", str(launcher_path))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_shutdown_event_name_is_stable_and_install_scoped():
    launcher = _load_launcher()

    first = launcher._shutdown_event_name(
        r"C:\\Program Files\\AAC Assistant\\AAC_Assistant.exe"
    )
    same = launcher._shutdown_event_name(
        r"C:\\Program Files\\AAC Assistant\\AAC_Assistant.exe"
    )
    other = launcher._shutdown_event_name(
        r"D:\\Portable\\AAC Assistant\\AAC_Assistant.exe"
    )

    assert first == same
    assert first.startswith("Local\\AACAssistantShutdown_")
    assert first != other


def test_browser_auto_open_can_be_disabled_for_headless_runs(monkeypatch):
    launcher = _load_launcher()

    for value in ("1", "true", "yes", "on"):
        monkeypatch.setenv("AAC_ASSISTANT_NO_BROWSER", value)
        assert launcher._should_open_browser() is False
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("AAC_ASSISTANT_NO_BROWSER", value)
        assert launcher._should_open_browser() is True


def test_headless_mode_never_calls_webbrowser(monkeypatch):
    launcher = _load_launcher()
    monkeypatch.setenv("AAC_ASSISTANT_NO_BROWSER", "1")
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)

    launcher._open_browser("http://127.0.0.1:8257/")

    assert opened == []


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
