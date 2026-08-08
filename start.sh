#!/usr/bin/env bash
# AAC Assistant Linux source-checkout launcher.
# Production serves the built SPA, API, uploads, and docs from one uvicorn process.
# Pass --dev explicitly to run uvicorn plus the Vite development server.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ -x ".venv/bin/python" ]]; then
    exec ".venv/bin/python" -m scripts.start_server "$@"
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run python -m scripts.start_server "$@"
fi

echo "ERROR: uv is not installed and .venv/bin/python was not found." >&2
echo "Install uv or create the project environment with: uv sync" >&2
exit 1
