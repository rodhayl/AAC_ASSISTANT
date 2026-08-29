"""Start the packaged AAC Assistant production server."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from contextlib import suppress
from pathlib import Path

_SHUTDOWN_EVENT_PREFIX = "Local\\AACAssistantShutdown_"
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258


def _startup_log_directories() -> list[Path]:
    """Return writable startup-log candidates in safest-first order."""
    candidates: list[Path] = []

    def add_candidate(candidate: object) -> None:
        """Add a path without allowing path discovery to mask startup errors."""
        try:
            resolved = Path(candidate).absolute()
        except (OSError, RuntimeError, TypeError):
            return
        if resolved not in candidates:
            candidates.append(resolved)

    try:
        from src import config

        add_candidate(config.RUNTIME_ROOT / "logs")
    except Exception as exc:
        # The config import may be the original startup failure. Do not use the
        # read-only Program Files directory as the first fallback.
        sys.stderr.write(
            f"Failed to import configuration while resolving log directories: {exc}\n"
        )

    appdata = os.environ.get("APPDATA")
    if appdata:
        add_candidate(Path(appdata) / "AACAssistant" / "logs")
    with suppress(OSError, RuntimeError):
        add_candidate(Path(tempfile.gettempdir()) / "AACAssistant" / "logs")
    add_candidate(Path(sys.executable).parent / "logs")
    return candidates


def _write_startup_error(message: str) -> None:
    """Persist a startup failure without masking it with a write error."""
    for log_dir in _startup_log_directories():
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "startup_error.log").write_text(message, encoding="utf-8")
            return
        except OSError:
            continue


def _shutdown_event_name(executable: str | None = None) -> str:
    """Return the per-install Windows event name used by the installer."""
    path = os.path.abspath(executable or sys.executable).replace("/", "\\").casefold()
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]
    return f"{_SHUTDOWN_EVENT_PREFIX}{digest}"


def _start_shutdown_watcher(server: object):
    """Watch the private Windows event and request a graceful Uvicorn exit.

    Returns an opaque cleanup tuple on Windows and ``None`` elsewhere. The
    event is scoped to the executable path, so an installer for one portable
    copy cannot request shutdown from another copy.
    """
    if os.name != "nt":
        return None

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateEventW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.CreateEventW(None, 1, 0, _shutdown_event_name())
        if not handle:
            return None
    except (AttributeError, OSError, TypeError):
        return None

    stop_watcher = threading.Event()

    def watch() -> None:
        try:
            while not stop_watcher.is_set():
                result = kernel32.WaitForSingleObject(handle, 1000)
                if result == _WAIT_OBJECT_0:
                    server.should_exit = True
                    return
                if result != _WAIT_TIMEOUT:
                    return
        except (OSError, AttributeError):
            return

    watcher = threading.Thread(target=watch, name="aac-shutdown-watcher", daemon=True)
    watcher.start()
    return handle, stop_watcher, watcher, kernel32


def _stop_shutdown_watcher(watcher_state) -> None:
    """Stop the event watcher and release its Windows handle."""
    if watcher_state is None:
        return
    handle, stop_watcher, watcher, kernel32 = watcher_state
    stop_watcher.set()
    watcher.join(timeout=2)
    with suppress(OSError, AttributeError):
        kernel32.CloseHandle(handle)


def _should_open_browser() -> bool:
    """Return whether desktop startup should open the local app automatically."""
    return os.environ.get("AAC_ASSISTANT_NO_BROWSER", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }


def _open_browser(url: str) -> None:
    """Open the local app for desktop users unless headless mode is enabled."""
    if _should_open_browser():
        webbrowser.open(url)


def _wait_for_server(url: str, timeout_seconds: float = 30.0) -> bool:
    """Wait until the local production server accepts HTTP requests."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    return False


def main() -> int:
    """Run Uvicorn in the foreground and open the local web application."""
    import uvicorn

    from src import config
    from src.api.main import app

    host = config.BACKEND_HOST
    port = config.BACKEND_PORT
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{port}/"

    from src.api.server import ShutdownAwareServer

    server = ShutdownAwareServer(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            timeout_graceful_shutdown=config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
            log_level="info",
            log_config=None,
        ),
        app=app,
    )
    shutdown_watcher = _start_shutdown_watcher(server)

    def run_server() -> None:
        try:
            server.run()
        except BaseException:
            _write_startup_error(traceback.format_exc())
            raise

    server_thread = threading.Thread(target=run_server, name="aac-uvicorn", daemon=True)
    server_thread.start()

    if not _wait_for_server(url):
        _write_startup_error(
            f"Server did not answer {url} within 30 seconds. "
            f"Server thread alive: {server_thread.is_alive()}"
        )
        server.should_exit = True
        server_thread.join(timeout=5)
        _stop_shutdown_watcher(shutdown_watcher)
        return 1

    _open_browser(url)
    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        server.should_exit = True
        server_thread.join(timeout=5)
    finally:
        _stop_shutdown_watcher(shutdown_watcher)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:
        _write_startup_error(traceback.format_exc())
        raise
