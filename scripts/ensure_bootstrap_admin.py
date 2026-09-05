"""
Ensure a bootstrap admin account exists for first-run local usage.

Behavior (no flags):
- Initializes DB schema and seed symbols/achievements.
- If an admin user already exists, does nothing.
- If an explicit AAC_BOOTSTRAP_ADMIN_PASSWORD is set, creates the administrator.
- If no admin exists and no password is set, reports that initial setup can be
  completed via the web interface (/setup) or configured in .env.

Usage:
    uv run python scripts/ensure_bootstrap_admin.py [--check]

Options:
    --check       Report whether the configured environment can create the
                  bootstrap admin without creating schema, symbols, or an
                  account (no database writes).
    -h, --help    Show this message and exit. ``--help`` never touches the
                  database; application modules load only after argument
                  parsing.

Bootstrap settings (env or env.properties via src.config):
- AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN (default: true)
- AAC_BOOTSTRAP_ADMIN_USERNAME (default: admin1)
- AAC_BOOTSTRAP_ADMIN_PASSWORD (default: unset; initial setup screen creates admin)

No password is ever printed to stdout/stderr or stored in plaintext.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make direct execution work from the repository root. The import is only a
# path adjustment; application/config modules remain deferred until after
# argparse so ``--help`` stays inert (importing ``src.config`` creates the
# data/logs/uploads directories as a side effect).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def ensure_bootstrap_admin() -> int:
    """Create the bootstrap administrator when configured; never prints secrets."""
    from src import config
    from src.aac_app.db import get_session
    from src.aac_app.models import User
    from src.aac_app.seed import init_database

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


def check_bootstrap_config() -> int:
    """Report configuration readiness without touching the database.

    Mirrors the configuration-only branches of ``ensure_bootstrap_admin``
    (enabled flag, production password acceptance, setup-screen fallback) so
    operators/CI can validate startup configuration without creating the
    schema or an account. Exit 1 means a normal run would abort on the same
    configuration.
    """
    from src import config
    from src.aac_app.services.auth_service import password_strength_error

    if not config.get_bool("AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN", True):
        print("Bootstrap admin creation disabled by AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=false")
        return 0

    username = config.get("AAC_BOOTSTRAP_ADMIN_USERNAME", "admin1").strip() or "admin1"
    explicit = config.explicit_bootstrap_password()
    is_production = str(config.ENVIRONMENT).strip().casefold() == "production"

    problem: str | None = None
    if is_production and explicit is None:
        problem = "a unique password must be configured"
    elif is_production:
        if explicit == config.DEFAULT_BOOTSTRAP_ADMIN_PASSWORD:
            problem = "the development default must be changed"
        else:
            problem = password_strength_error(explicit)
    if problem is not None:
        print(
            "ERROR: AAC_BOOTSTRAP_ADMIN_PASSWORD is not acceptable in production: "
            + problem,
            file=sys.stderr,
        )
        print(
            "Fix AAC_BOOTSTRAP_ADMIN_PASSWORD (or set "
            "AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=false) and re-run.",
            file=sys.stderr,
        )
        return 1

    if explicit is not None or config._is_test_environment():
        print("Bootstrap admin ready.")
        print(f"Username: {username}")
        return 0

    print("No administrator account exists and no AAC_BOOTSTRAP_ADMIN_PASSWORD is set.")
    print("Complete initial setup via the web interface at http://127.0.0.1:8086/setup")
    print("or configure AAC_BOOTSTRAP_ADMIN_PASSWORD in .env.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the selected mode; parsing happens before any application import."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "report whether the configured environment can create the bootstrap "
            "admin without creating the schema or an account"
        ),
    )
    args = parser.parse_args(argv)
    if args.check:
        return check_bootstrap_config()
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
