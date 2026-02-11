
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.aac_app.models.database import get_session  # noqa: E402
from src.aac_app.services.user_service import UserService  # noqa: E402


def _get_password() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()

    env_password = os.environ.get("AAC_ADMIN_RESET_PASSWORD", "").strip()
    if env_password:
        return env_password

    raise SystemExit(
        "Usage: python src/scripts/reset_admin.py <new_password>\n"
        "Or set AAC_ADMIN_RESET_PASSWORD."
    )


def reset_admin():
    new_password = _get_password()
    print("Resetting admin password...")
    with get_session() as session:
        service = UserService()
        if service.reset_password_for_username(session, "admin1", new_password):
            print("Success: Password for 'admin1' was reset.")
        else:
            print("Error: User 'admin1' not found")


if __name__ == "__main__":
    reset_admin()
