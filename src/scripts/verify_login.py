
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.aac_app.models.database import get_session, User  # noqa: E402
from src.aac_app.services.auth_service import get_password_hash, verify_password  # noqa: E402


def _get_password() -> str:
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--") and sys.argv[1].strip():
        return sys.argv[1].strip()
    env_password = os.environ.get("AAC_ADMIN_VERIFY_PASSWORD", "").strip()
    if env_password:
        return env_password
    raise SystemExit(
        "Usage: python src/scripts/verify_login.py <password> [--fix]\n"
        "Or set AAC_ADMIN_VERIFY_PASSWORD."
    )


def verify_login():
    candidate_password = _get_password()
    print("Verifying admin login...")
    with get_session() as session:
        user = session.query(User).filter(User.username == "admin1").first()
        if user:
            print(f"User found: {user.username}")

            # Test password verification
            is_valid = verify_password(candidate_password, user.password_hash)
            print(f"Provided password valid? {is_valid}")

            if not is_valid:
                print("Password check failed.")
                if "--fix" in sys.argv:
                    print("Resetting hash again...")
                    user.password_hash = get_password_hash(candidate_password)
                    session.commit()
                    print("New hash set.")
                    print(f"Re-verify: {verify_password(candidate_password, user.password_hash)}")
                else:
                    print("Run with --fix to reset password to the provided value.")
        else:
            print("User not found")


if __name__ == "__main__":
    verify_login()
