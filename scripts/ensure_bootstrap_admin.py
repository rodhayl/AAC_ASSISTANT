"""
Ensure a bootstrap admin account exists for first-run local usage.

Behavior:
- Initializes DB schema if needed.
- If an admin user already exists, does nothing.
- If no admin user exists, creates one using bootstrap settings.

Bootstrap settings (env or env.properties via src.config):
- AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN (default: true)
- AAC_BOOTSTRAP_ADMIN_USERNAME (default: admin1)
- AAC_BOOTSTRAP_ADMIN_PASSWORD (default: Admin123)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src import config  # noqa: E402
from src.aac_app.models.database import User, get_session, init_database  # noqa: E402
from src.aac_app.services.auth_service import get_password_hash  # noqa: E402


def _read_bool(key: str, default: bool) -> bool:
    return config.get_bool(key, default)


def _read_str(key: str, default: str) -> str:
    value = config.get(key, default).strip()
    return value if value else default


def ensure_bootstrap_admin() -> int:
    enabled = _read_bool("AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN", True)
    if not enabled:
        print("Bootstrap admin creation disabled by AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=false")
        return 0

    username = _read_str("AAC_BOOTSTRAP_ADMIN_USERNAME", "admin1")
    password = _read_str("AAC_BOOTSTRAP_ADMIN_PASSWORD", "Admin123")

    # Ensure DB/tables exist first.
    init_database()

    with get_session() as session:
        existing_admin = session.query(User).filter(User.user_type == "admin").first()
        if existing_admin:
            print(f"Admin user already exists: {existing_admin.username}")
            return 0

        user = session.query(User).filter(User.username == username).first()
        if user:
            user.user_type = "admin"
            user.is_active = True
            user.password_hash = get_password_hash(password)
            if not user.display_name:
                user.display_name = "Administrator"
            action = "promoted existing user to admin"
        else:
            user = User(
                username=username,
                display_name="Administrator",
                user_type="admin",
                password_hash=get_password_hash(password),
                is_active=True,
            )
            session.add(user)
            action = "created new bootstrap admin"

        session.commit()
        print("Bootstrap admin ready.")
        print(f"Action: {action}")
        print(f"Username: {username}")
        print(f"Password: {password}")
        print("IMPORTANT: Change this password immediately after first login.")

    return 0


if __name__ == "__main__":
    raise SystemExit(ensure_bootstrap_admin())
