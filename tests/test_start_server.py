import asyncio
import signal
import subprocess
import sys
from pathlib import Path

import uvicorn

from scripts import start_server


def test_sigterm_requests_graceful_child_shutdown(monkeypatch):
    """SIGTERM uses the same bounded child cleanup as Ctrl+C."""
    registered = {}
    restored = {}

    def fake_signal(signum, handler):
        if signum in registered and handler is not registered[signum]:
            restored[signum] = handler
        else:
            registered[signum] = handler
        return None

    monkeypatch.setattr(start_server.signal, "signal", fake_signal)
    monkeypatch.setattr(start_server.signal, "getsignal", lambda _signum: None)

    class FakeProcess:
        def __init__(self):
            self.poll_count = 0
            self.terminated = False

        def poll(self):
            self.poll_count += 1
            if self.poll_count == 1:
                registered[signal.SIGTERM](signal.SIGTERM, None)
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def send_signal(self, _signum):
            self.terminated = True

        def wait(self, timeout):
            assert timeout >= 0
            return 0

    process = FakeProcess()
    result = start_server._wait_for_process_with_signal_handling(process, timeout=5)

    assert result == 0
    assert process.terminated is True
    assert signal.SIGTERM in registered
    assert restored[signal.SIGTERM] is None


def test_shutdown_aware_server_signals_app_before_uvicorn_shutdown(monkeypatch):
    from src.api.main import app
    from src.api.server import ShutdownAwareServer

    shutdown_event = asyncio.Event()
    original_event = getattr(app.state, "shutdown_event", None)
    app.state.shutdown_event = shutdown_event
    calls = []

    async def fake_shutdown(_server, *args, **kwargs):
        calls.append(shutdown_event.is_set())

    monkeypatch.setattr(uvicorn.Server, "shutdown", fake_shutdown)
    try:
        server = ShutdownAwareServer(uvicorn.Config(app), app=app)
        asyncio.run(server.shutdown())
    finally:
        app.state.shutdown_event = original_event

    assert calls == [True]


def test_run_server_supports_direct_and_module_help_invocation():
    """The documented server entry point works in both Python invocation modes."""
    repo_root = Path(__file__).resolve().parents[1]
    for command in (
        [sys.executable, "-m", "scripts.run_server", "--help"],
        [sys.executable, "scripts/run_server.py", "--help"],
    ):
        result = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "Run the production Uvicorn server" in result.stdout


def test_server_command_includes_graceful_shutdown_timeout(monkeypatch):
    monkeypatch.setattr(start_server.config, "BACKEND_HOST", "127.0.0.1")
    monkeypatch.setattr(start_server.config, "BACKEND_PORT", 8099)
    monkeypatch.setattr(start_server.config, "BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", 12)

    command = start_server._server_command()

    assert "--timeout-graceful-shutdown" in command
    timeout_index = command.index("--timeout-graceful-shutdown")
    assert command[timeout_index + 1] == "12"
