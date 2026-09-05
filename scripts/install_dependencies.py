"""Unattended uv-based installation and frontend preparation."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# ``uv run python scripts/install_dependencies.py`` places ``scripts`` first
# on sys.path, so explicitly make the repository root importable.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def ensure_configuration(project_root: Path) -> tuple[Path, str]:
    """Create the canonical dotenv file and repair its JWT secret in place."""
    from src import config

    env_path = config.ensure_env_file(project_root)
    return env_path, config.ensure_jwt_secret(env_path)


def frontend_build_commands(
    project_root: Path,
    npm_command: str = "npm",
) -> list[tuple[list[str], Path]]:
    """Return the deterministic npm commands used for a production frontend."""
    frontend_dir = project_root / "src" / "frontend"
    return [
        ([npm_command, "ci"], frontend_dir),
        ([npm_command, "run", "build"], frontend_dir),
    ]


def _npm_command() -> str | None:
    """Resolve npm only when the installer is actually running."""
    from src.aac_app.utils.runtime import npm_command

    return npm_command()


def sync_python(project_root: Path, include_voice: bool) -> None:
    """Install the core uv project, optionally adding the voice extra."""
    command = ["uv", "sync"]
    if include_voice:
        command.append("--extra")
        command.append("voice")
    subprocess.run(command, cwd=project_root, check=True)


def build_frontend_if_available(project_root: Path) -> bool:
    """Build the SPA when Node/npm are installed, otherwise skip cleanly."""
    node = shutil.which("node")
    npm = _npm_command()
    if node is None or npm is None:
        print("Node.js/npm not found; skipping the optional frontend build.")
        print("Install Node.js and rerun this installer to create src/frontend/dist/.")
        return False

    for command, cwd in frontend_build_commands(project_root, npm):
        print(f"Running {' '.join(command)} in {cwd}")
        subprocess.run(command, cwd=cwd, check=True)
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse installer options without prompting for input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--voice",
        action="store_true",
        help="also install the optional faster-whisper voice dependencies",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="skip npm ci and npm run build even when Node.js is available",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="skip uv sync because the batch shim already ran it",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the complete unattended installation flow."""
    args = parse_args(argv)
    from src import config

    project_root = config.PROJECT_ROOT
    try:
        print(f"Installing AAC Assistant from {project_root}")
        if not args.skip_sync:
            sync_python(project_root, include_voice=args.voice)
        env_path, secret = ensure_configuration(project_root)
        print(f"Configuration ready: {env_path} (JWT secret length: {len(secret)})")

        if not args.skip_frontend:
            build_frontend_if_available(project_root)
        else:
            print("Skipping the optional frontend build (--skip-frontend).")
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: installation step failed: {exc}", file=sys.stderr)
        return exc.returncode if isinstance(exc, subprocess.CalledProcessError) else 1

    print()
    print("Installation complete.")
    print("Next steps:")
    print("  start.bat                 Start the production app on http://127.0.0.1:8086")
    print("  start.bat --dev           Run uvicorn plus the Vite development server")
    print("  uv sync --extra voice     Add optional faster-whisper voice support")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
