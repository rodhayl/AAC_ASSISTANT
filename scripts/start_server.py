"""Start AAC Assistant in production or explicit development mode."""

from __future__ import annotations

import argparse
import hashlib
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# Make direct execution work from the repository root:
# ``uv run python scripts/start_server.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.aac_app.utils.runtime import npm_command  # noqa: E402


def is_port_available(host: str, port: int) -> bool:
    """Return whether a local TCP port has no active listener."""
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((probe_host, port)) != 0


_npm_command = npm_command


def _frontend_dependencies_need_install(frontend_dir: Path) -> bool:
    """Return whether npm dependencies are absent or out of sync with the lockfile.

    Uses a content hash of package-lock.json so git operations that touch
    file mtimes (checkout, merge, pull) do not force a reinstall.
    """
    node_modules = frontend_dir / "node_modules"
    if not node_modules.is_dir():
        return True

    lockfile = frontend_dir / "package-lock.json"
    if not lockfile.is_file():
        return True

    hash_stamp = node_modules / ".package-lock-hash"
    current_hash = hashlib.sha256(lockfile.read_bytes()).hexdigest()

    if not hash_stamp.is_file():
        return True

    return hash_stamp.read_text().strip() != current_hash


def _write_dependency_hash_stamp(frontend_dir: Path) -> None:
    """Store the current package-lock.json hash so the next startup can skip npm ci."""
    lockfile = frontend_dir / "package-lock.json"
    hash_stamp = frontend_dir / "node_modules" / ".package-lock-hash"
    hash_stamp.write_text(hashlib.sha256(lockfile.read_bytes()).hexdigest())


def ensure_frontend_build() -> Path:
    """Return a current built frontend, rebuilding it when source changed."""
    frontend_dir = config.PROJECT_ROOT / "src" / "frontend"
    dist_dir = frontend_dir / "dist"
    prebuilt_candidates = (
        dist_dir,
        config.PROJECT_ROOT / "frontend",
        config.PROJECT_ROOT / "dist",
        config.BUNDLE_DIR / "frontend",
    )
    for candidate in prebuilt_candidates:
        index_file = candidate / "index.html"
        if not index_file.is_file():
            continue
        # A checked-in/stale dist directory otherwise hides frontend changes
        # forever because production startup only checks for index.html.
        # Compare application sources, not tests or node_modules, so a normal
        # restart rebuilds only when the served SPA actually changed.
        if candidate == dist_dir:
            built_at = index_file.stat().st_mtime
            source_roots = (frontend_dir / "src", frontend_dir / "public")
            source_files = [frontend_dir / "index.html", frontend_dir / "package.json"]
            for root in source_roots:
                if root.is_dir():
                    source_files.extend(path for path in root.rglob("*") if path.is_file())
            if all(path.stat().st_mtime <= built_at for path in source_files if path.exists()):
                return candidate
        else:
            return candidate

    npm = _npm_command()
    if npm is None:
        raise RuntimeError(
            "The production frontend is missing at "
            f"{dist_dir}. Install Node.js to build it, or ship a prebuilt dist/ folder."
        )

    if _frontend_dependencies_need_install(frontend_dir):
        lockfile_hash = hashlib.sha256(
            (frontend_dir / "package-lock.json").read_bytes()
        ).hexdigest()[:8]
        print(f"Installing Node dependencies (lockfile {lockfile_hash}) before building the production frontend.")
        subprocess.run(
            [npm, "ci", "--prefer-offline", "--no-audit", "--no-fund"],
            cwd=frontend_dir,
            check=True,
        )
        _write_dependency_hash_stamp(frontend_dir)
    else:
        print("Node dependencies are up to date; rebuilding the production frontend.")
    subprocess.run([npm, "run", "build"], cwd=frontend_dir, check=True)
    if not (dist_dir / "index.html").is_file():
        raise RuntimeError(f"Frontend build completed without creating {dist_dir}.")
    return dist_dir


def ensure_bootstrap_admin() -> None:
    """Run the idempotent first-run database/bootstrap preparation."""
    script = config.PROJECT_ROOT / "scripts" / "ensure_bootstrap_admin.py"
    subprocess.run([sys.executable, str(script)], cwd=config.PROJECT_ROOT, check=True)


def _server_command() -> list[str]:
    """Build the uvicorn command from the typed backend configuration."""
    return [
        sys.executable,
        "-m",
        "scripts.run_server",
        "--host",
        str(config.BACKEND_HOST),
        "--port",
        str(config.BACKEND_PORT),
        "--timeout-graceful-shutdown",
        str(config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS),
    ]


def _process_creationflags() -> int:
    """Use a separate process group on Windows so Ctrl+C handling is predictable."""
    if os.name == "nt":
        return subprocess.CREATE_NEW_PROCESS_GROUP
    return 0


def _stop_process_gracefully(process: subprocess.Popen[bytes] | subprocess.Popen[str], *, timeout: int) -> None:
    """Ask a child process to stop, then escalate if it does not exit."""
    if process.poll() is not None:
        return

    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.terminate()

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_for_process_with_signal_handling(
    process: subprocess.Popen[bytes] | subprocess.Popen[str],
    *,
    timeout: int,
) -> int:
    """Wait for a child while handling Ctrl+C / Ctrl+Break ourselves."""
    shutdown_requested = threading.Event()
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    previous_sigbreak = signal.getsignal(signal.SIGBREAK) if hasattr(signal, "SIGBREAK") else None

    def _request_shutdown(_signum, _frame):
        shutdown_requested.set()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_shutdown)

    try:
        while True:
            returncode = process.poll()
            if returncode is not None:
                return returncode
            if shutdown_requested.is_set():
                _stop_process_gracefully(process, timeout=timeout)
                return 0
            time.sleep(0.1)
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        if hasattr(signal, "SIGBREAK") and previous_sigbreak is not None:
            signal.signal(signal.SIGBREAK, previous_sigbreak)


def run_production() -> int:
    """Build/prep once, then run exactly one uvicorn process."""
    if not is_port_available(str(config.BACKEND_HOST), config.BACKEND_PORT):
        print(
            f"ERROR: port {config.BACKEND_PORT} is already in use. "
            "Stop the existing service or configure BACKEND_PORT before starting AAC Assistant.",
            file=sys.stderr,
        )
        return 1

    ensure_frontend_build()
    ensure_bootstrap_admin()

    print(
        f"Starting AAC Assistant on http://127.0.0.1:{config.BACKEND_PORT} "
        f"(bind {config.BACKEND_HOST}:{config.BACKEND_PORT})"
    )
    backend = subprocess.Popen(
        _server_command(),
        cwd=config.PROJECT_ROOT,
        creationflags=_process_creationflags(),
    )
    try:
        return _wait_for_process_with_signal_handling(
            backend,
            timeout=max(config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS + 2, 5),
        )
    finally:
        if backend.poll() is None:
            backend.kill()
            backend.wait(timeout=5)


def run_development() -> int:
    """Run uvicorn and Vite as the explicitly requested development flow."""
    npm = _npm_command()
    if npm is None:
        print("ERROR: --dev requires Node.js/npm on PATH.", file=sys.stderr)
        return 1

    if not is_port_available(str(config.BACKEND_HOST), config.BACKEND_PORT):
        print(
            f"ERROR: port {config.BACKEND_PORT} is already in use. "
            "Stop the existing service or configure BACKEND_PORT before starting AAC Assistant.",
            file=sys.stderr,
        )
        return 1

    ensure_bootstrap_admin()
    backend = subprocess.Popen(
        _server_command(),
        cwd=config.PROJECT_ROOT,
        creationflags=_process_creationflags(),
    )
    frontend_dir = config.PROJECT_ROOT / "src" / "frontend"
    frontend = subprocess.Popen(
        [
            npm,
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(config.FRONTEND_PORT),
        ],
        cwd=frontend_dir,
    )

    try:
        return _wait_for_process_with_signal_handling(
            backend,
            timeout=max(config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS + 2, 5),
        )
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                if process is backend:
                    _stop_process_gracefully(
                        process,
                        timeout=max(config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS + 2, 5),
                    )
                else:
                    process.terminate()
        for process in (frontend, backend):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def parse_args() -> argparse.Namespace:
    """Parse launcher flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dev",
        action="store_true",
        help="run uvicorn plus the Vite development server",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="build/prep production assets without starting uvicorn",
    )
    return parser.parse_args()


def main() -> int:
    """Run the selected launcher mode."""
    args = parse_args()
    try:
        if args.dev:
            return run_development()
        if args.prepare_only:
            ensure_frontend_build()
            ensure_bootstrap_admin()
            print("Production preparation completed successfully.")
            return 0
        return run_production()
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        return exc.returncode or 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
