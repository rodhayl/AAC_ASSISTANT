"""
Ensure a bootstrap admin account exists for first-run local usage.

Behavior:
- Initializes DB schema and seed symbols/achievements.
- If an admin user already exists, does nothing.
- If an explicit AAC_BOOTSTRAP_ADMIN_PASSWORD is set, creates the administrator.
- If no admin exists and no password is set, reports that initial setup can be
  completed via the web interface (/setup) or configured in .env.

Bootstrap settings (env or env.properties via src.config):
- AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN (default: true)
- AAC_BOOTSTRAP_ADMIN_USERNAME (default: admin1)
- AAC_BOOTSTRAP_ADMIN_PASSWORD (default: unset; initial setup screen creates admin)

No password is ever printed to stdout/stderr or stored in plaintext.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src import config  # noqa: E402
from src.aac_app.db import get_session  # noqa: E402
from src.aac_app.models import User  # noqa: E402
from src.aac_app.seed import init_database  # noqa: E402


def ensure_bootstrap_admin() -> int:
    enabled = config.get_bool("AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN", True)
    if not enabled:
        print("Bootstrap admin creation disabled by AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=false")
        return 0

    username = config.get("AAC_BOOTSTRAP_ADMIN_USERNAME", "admin1").strip() or "admin1"

    # init_database performs the idempotent bootstrap (schema + optional admin creation)
    init_database(ensure_schema=True)

    with get_session() as session:
        admin = session.query(User).filter(User.user_type == "admin").first()
        if admin is not None:
            print(f"Admin user already exists: {admin.username}")
            return 0

    if config.explicit_bootstrap_password() is None and not config._is_test_environment():
        print("No administrator account exists and no AAC_BOOTSTRAP_ADMIN_PASSWORD is set.")
        print("Complete initial setup via the web interface at http://127.0.0.1:8086/setup")
        print("or configure AAC_BOOTSTRAP_ADMIN_PASSWORD in .env.")
        return 0

    print("Bootstrap admin ready.")
    print(f"Username: {username}")
    return 0


def main() -> int:
    try:
        return ensure_bootstrap_admin()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        print(
            "Fix AAC_BOOTSTRAP_ADMIN_PASSWORD (or set "
            "AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=false) and re-run.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
