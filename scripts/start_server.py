"""Start AAC Assistant in production or explicit development mode."""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# Make direct execution work from the repository root:
# ``uv run python scripts/start_server.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config


def is_port_available(host: str, port: int) -> bool:
    """Return whether a local TCP port has no active listener."""
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((probe_host, port)) != 0


def _npm_command() -> str | None:
    """Find the Windows npm shim or a platform-neutral npm executable."""
    return shutil.which("npm.cmd") or shutil.which("npm")


def ensure_frontend_build() -> Path:
    """Return the built frontend directory, building it when Node is available."""
    frontend_dir = config.PROJECT_ROOT / "src" / "frontend"
    dist_dir = frontend_dir / "dist"
    prebuilt_candidates = (
        dist_dir,
        config.PROJECT_ROOT / "frontend",
        config.PROJECT_ROOT / "dist",
        config.BUNDLE_DIR / "frontend",
    )
    for candidate in prebuilt_candidates:
        if (candidate / "index.html").is_file():
            return candidate

    npm = _npm_command()
    if npm is None:
        raise RuntimeError(
            "The production frontend is missing at "
            f"{dist_dir}. Install Node.js to build it, or ship a prebuilt dist/ folder."
        )

    print("Production frontend is missing; installing Node dependencies and building it.")
    subprocess.run([npm, "ci"], cwd=frontend_dir, check=True)
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
        "uvicorn",
        "src.api.main:app",
        "--host",
        str(config.BACKEND_HOST),
        "--port",
        str(config.BACKEND_PORT),
    ]


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
    completed = subprocess.run(_server_command(), cwd=config.PROJECT_ROOT)
    return completed.returncode


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
    backend = subprocess.Popen(_server_command(), cwd=config.PROJECT_ROOT)
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
        return backend.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
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
