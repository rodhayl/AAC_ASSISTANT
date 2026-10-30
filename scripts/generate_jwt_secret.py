"""Generate a strong JWT secret for local config bootstrap."""

from __future__ import annotations

import secrets


def main() -> int:
    print(secrets.token_hex(32))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
