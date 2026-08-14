"""
Ensure a bootstrap admin account exists for first-run local usage.

Behavior:
- Initializes DB schema if needed.
- If an admin user already exists, does nothing.
- If no admin user exists, creates one using bootstrap settings.

Bootstrap settings (env or env.properties via src.config):
- AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN (default: true)
- AAC_BOOTSTRAP_ADMIN_USERNAME (default: admin1)
- AAC_BOOTSTRAP_ADMIN_PASSWORD (development default generates a random one-time
  credential stored in .env; production requires an explicit strong password)

The password is never printed. A generated one-time credential is stored in
``.env`` and must be changed after first login.
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

    # init_database performs the idempotent bootstrap (schema + admin creation)
    # using the shared seed logic, so there is a single source of truth for how
    # the first administrator is created.
    init_database(ensure_schema=True)

    with get_session() as session:
        admin = session.query(User).filter(User.user_type == "admin").first()
        if admin is not None:
            print(f"Admin user already exists: {admin.username}")
        else:
            print(
                "Bootstrap admin was not created. Check the application log and "
                "the bootstrap settings in .env."
            )
            return 1

    print("Bootstrap admin ready.")
    print(f"Username: {username}")
    if config.explicit_bootstrap_password() is None:
        print("Default development credentials were used.")
        print("IMPORTANT: Set AAC_BOOTSTRAP_ADMIN_PASSWORD in .env or change it immediately after first login.")
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
