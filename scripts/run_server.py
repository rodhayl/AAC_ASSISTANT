"""Run the production Uvicorn server with application-aware shutdown."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make direct execution work from the repository root:
# ``uv run python scripts/run_server.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> None:
    """Parse options before importing the application and run one server process."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--timeout-graceful-shutdown", type=int)
    args = parser.parse_args(argv)

    # Keep --help informational: importing src.api.main configures logging,
    # creates runtime directories, and imports the complete router graph.
    # Resolve those application resources only after argparse accepts a normal
    # server invocation.
    import uvicorn

    from src import config
    from src.api.main import app
    from src.api.server import ShutdownAwareServer

    server = ShutdownAwareServer(
        uvicorn.Config(
            app,
            host=(args.host if args.host is not None else config.BACKEND_HOST),
            port=(args.port if args.port is not None else config.BACKEND_PORT),
            timeout_graceful_shutdown=(
                args.timeout_graceful_shutdown
                if args.timeout_graceful_shutdown is not None
                else config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
            ),
        ),
        app=app,
    )
    server.run()


if __name__ == "__main__":
    main()
