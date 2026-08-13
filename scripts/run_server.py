"""Run the production Uvicorn server with application-aware shutdown."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make direct execution work from the repository root:
# ``uv run python scripts/run_server.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

from src import config  # noqa: E402
from src.api.main import app
from src.api.server import ShutdownAwareServer


def main() -> None:
    """Run one production server process."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=config.BACKEND_HOST)
    parser.add_argument("--port", type=int, default=config.BACKEND_PORT)
    parser.add_argument(
        "--timeout-graceful-shutdown",
        type=int,
        default=config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
    )
    args = parser.parse_args()
    server = ShutdownAwareServer(
        uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            timeout_graceful_shutdown=args.timeout_graceful_shutdown,
        ),
        app=app,
    )
    server.run()


if __name__ == "__main__":
    main()
