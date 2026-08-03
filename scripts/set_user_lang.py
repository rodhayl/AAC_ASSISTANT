import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aac_app.models.database import User  # noqa: E402


def set_user_language(lang_code):
    print(f"Setting user language to: {lang_code}")

    engine = create_engine(
        f"sqlite:///{os.path.join(os.getcwd(), 'data', 'aac_assistant.db')}"
    )
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        user = session.query(User).first()
        if not user:
            print("No user found.")
            return

        # User settings are stored in a JSON column or separate table?
        # Looking at User model: settings = relationship("UserPreferences", uselist=False, back_populates="user")
        # Wait, UserPreferences is a table.

        from src.aac_app.models.database import UserSettings

        prefs = session.query(UserSettings).filter_by(user_id=user.id).first()
        if not prefs:
            prefs = UserSettings(user_id=user.id)
            session.add(prefs)

        prefs.ui_language = lang_code
        session.commit()
        print(f"Updated user {user.username} preferences: ui_language={lang_code}")

    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        lang = sys.argv[1]
        set_user_language(lang)
    else:
        print("Usage: python set_user_lang.py <lang_code>")
