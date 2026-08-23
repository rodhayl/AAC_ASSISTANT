#!/usr/bin/env bash
# AAC Assistant Linux source-checkout launcher.
# Production serves the built SPA, API, uploads, and docs from one uvicorn process.
# Pass --dev explicitly to run uvicorn plus the Vite development server.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

UV_CMD=""

resolve_uv() {
    if command -v uv >/dev/null 2>&1; then
        UV_CMD="$(command -v uv)"
        return 0
    fi

    # The official installer does not modify the current shell's PATH.
    # Check its documented locations before and after bootstrapping it.
    if [[ -n "${HOME:-}" && -x "$HOME/.local/bin/uv" ]]; then
        UV_CMD="$HOME/.local/bin/uv"
        return 0
    fi
    if [[ -n "${HOME:-}" && -x "$HOME/.cargo/bin/uv" ]]; then
        UV_CMD="$HOME/.cargo/bin/uv"
        return 0
    fi
    return 1
}

bootstrap_uv() {
    echo "uv was not found; installing it automatically..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "ERROR: automatic uv installation requires curl or wget." >&2
        return 1
    fi
}

resolve_uv || {
    bootstrap_uv && resolve_uv
}

if [[ -n "$UV_CMD" ]]; then
    UV_SYNC_ARGS=(--no-dev --extra voice --extra tts)
    if "$UV_CMD" run --no-sync python -m scripts.check_dev_dependencies >/dev/null 2>&1; then
        # The check is deliberately before sync: --no-dev would otherwise
        # prune an already-installed dev group before we could avoid asking.
        UV_SYNC_ARGS=(--group dev --extra voice --extra tts)
    elif [[ -t 0 && -t 1 ]]; then
        read -r -p "Development dependencies are missing. Install them? [y/N] " install_dev
        case "${install_dev,,}" in
            y|yes) UV_SYNC_ARGS=(--group dev --extra voice --extra tts) ;;
        esac
    else
        echo "Development dependencies are missing; skipping them in non-interactive mode."
    fi

    echo "Creating/updating the Python environment and installing dependencies..."
    "$UV_CMD" sync "${UV_SYNC_ARGS[@]}"
    echo "Preparing voice dependencies and Kokoro model..."
    "$UV_CMD" run --no-sync python -m scripts.ensure_voice_runtime
    exec "$UV_CMD" run --no-sync python -m scripts.start_server "$@"
fi

if [[ -x ".venv/bin/python" ]]; then
    # Offline fallback for an already provisioned checkout when uv itself is
    # temporarily unavailable. A fresh checkout never reaches this branch.
    echo "uv is unavailable; using the existing Python environment."
    ".venv/bin/python" -m scripts.ensure_voice_runtime
    exec ".venv/bin/python" -m scripts.start_server "$@"
fi

echo "ERROR: uv could not be installed automatically and no .venv/bin/python exists." >&2
echo "Install uv manually or install curl/wget, then run start.sh again." >&2
exit 1
