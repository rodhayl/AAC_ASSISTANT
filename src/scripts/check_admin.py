
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.aac_app.models.database import get_session, User  # noqa: E402
from src.aac_app.services.auth_service import get_password_hash  # noqa: E402


def _get_reset_password() -> str:
    if "--password" in sys.argv:
        idx = sys.argv.index("--password")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].strip():
            return sys.argv[idx + 1].strip()
    env_password = os.environ.get("AAC_ADMIN_RESET_PASSWORD", "").strip()
    if env_password:
        return env_password
    raise SystemExit(
        "When using --reset, provide --password <new_password> "
        "or set AAC_ADMIN_RESET_PASSWORD."
    )


def check_admin(reset=False):
    print("Checking admin user...")
    with get_session() as session:
        user = session.query(User).filter(User.username == "admin1").first()
        if user:
            print(f"Found user: {user.username}, type: {user.user_type}")
            if reset:
                user.password_hash = get_password_hash(_get_reset_password())
                session.commit()
                print("Password reset manually.")
            else:
                print("User exists. Pass --reset to reset password.")
        else:
            print("User admin1 NOT found.")


if __name__ == "__main__":
    import sys
    reset = "--reset" in sys.argv
    check_admin(reset=reset)
