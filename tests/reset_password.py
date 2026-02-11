import os
import sys

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aac_app.models.database import User  # noqa: E402


def reset_password(username, new_password):
    print(f"Resetting password for {username}...")

    engine = create_engine(
        f"sqlite:///{os.path.join(os.getcwd(), 'data', 'aac_assistant.db')}"
    )
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        if username:
            user = session.query(User).filter_by(username=username).first()
        else:
            user = session.query(User).first()
            if user:
                print(f"No username provided, using first user found: {user.username}")

        if not user:
            print(f"User {username} not found.")
            return

        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(new_password.encode("utf-8"), salt)
        user.password_hash = hashed.decode("utf-8")

        session.commit()
        print(f"Password for {user.username} reset successfully.")

    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    reset_password(None, "password123")
