
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.aac_app.models.database import get_session  # noqa: E402
from src.aac_app.services.user_service import UserService  # noqa: E402


def _get_password() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    env_password = os.environ.get("AAC_TEACHER_RESET_PASSWORD", "").strip()
    if env_password:
        return env_password
    raise SystemExit(
        "Usage: python src/scripts/reset_teacher_password.py <new_password>\n"
        "Or set AAC_TEACHER_RESET_PASSWORD."
    )


def reset_pass():
    new_password = _get_password()
    print("Resetting password for teacher1...")
    with get_session() as session:
        service = UserService()
        result = service.reset_password_for_username(session, "teacher1", new_password)
        if result:
            print("Password reset successful.")
        else:
            print("User not found.")


if __name__ == "__main__":
    reset_pass()
