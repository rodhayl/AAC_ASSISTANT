"""Start the packaged AAC Assistant production server."""

from __future__ import annotations

import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def _write_startup_error(message: str) -> None:
    """Persist a startup failure where the user can report it."""
    try:
        from src import config

        log_dir = config.RUNTIME_ROOT / "logs"
    except Exception:
        log_dir = Path(sys.executable).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "startup_error.log").write_text(message, encoding="utf-8")


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

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            log_config=None,
        )
    )

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
        return 1

    webbrowser.open(url)
    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        server.should_exit = True
        server_thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:
        _write_startup_error(traceback.format_exc())
        raise
