"""Create or repair the canonical ``.env`` JWT secret."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# When executed as ``python scripts/generate_jwt_secret.py``, Python puts the
# scripts directory on sys.path rather than the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import ensure_env_file, ensure_jwt_secret


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to the canonical dotenv file (default: .env)",
    )
    args = parser.parse_args()

    env_path = args.env_file.absolute()
    if env_path.name == ".env" and not env_path.exists():
        ensure_env_file(env_path.parent)
    secret = ensure_jwt_secret(env_path)
    print(secret)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
