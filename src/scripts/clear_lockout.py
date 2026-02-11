
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.aac_app.models.database import get_session  # noqa: E402
from src.aac_app.services.lockout_service import lockout_service  # noqa: E402


def clear_lockout():
    print("Clearing lockout for admin1...")
    with get_session() as session:
        lockout_service.reset_attempts(session, "admin1")
        print("Lockout cleared.")


if __name__ == "__main__":
    clear_lockout()
