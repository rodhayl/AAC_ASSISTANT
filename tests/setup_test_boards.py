import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aac_app.models.database import (  # noqa: E402
    BoardSymbol,
    CommunicationBoard,
    Symbol,
    User,
)


def setup_test_data():
    print("Setting up test data...")

    # Connect to DB
    engine = create_engine(
        f"sqlite:///{os.path.join(os.getcwd(), 'data', 'aac_assistant.db')}"
    )
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get a user (assuming id 1 exists, or get first)
        user = session.query(User).first()
        if not user:
            print("No user found. Please run the app once to create a user.")
            return

        print(f"Using user: {user.username} (ID: {user.id})")

        # 1. Create Symbols if they don't exist
        # Apple (English)
        apple = session.query(Symbol).filter_by(label="Apple").first()
        if not apple:
            apple = Symbol(
                label="Apple",
                category="food",
                language="en",
                is_builtin=True,
                image_path="/static/symbols/apple.png",
            )
            session.add(apple)

        # Dog (English)
        dog = session.query(Symbol).filter_by(label="Dog").first()
        if not dog:
            dog = Symbol(
                label="Dog",
                category="animals",
                language="en",
                is_builtin=True,
                image_path="/static/symbols/dog.png",
            )
            session.add(dog)

        session.commit()

        # Refresh
        apple = session.query(Symbol).filter_by(label="Apple").first()
        dog = session.query(Symbol).filter_by(label="Dog").first()

        # 2. Create Boards

        # Board A: Playable (2 symbols) - Normal
        board_playable = CommunicationBoard(
            user_id=user.id,
            name="Test: Playable Board",
            description="Should appear in playable section",
            category="test",
            locale="en",
            is_language_learning=False,
        )
        session.add(board_playable)
        session.flush()  # get ID

        session.add(
            BoardSymbol(
                board_id=board_playable.id,
                symbol_id=apple.id,
                position_x=0,
                position_y=0,
                is_visible=True,
            )
        )
        session.add(
            BoardSymbol(
                board_id=board_playable.id,
                symbol_id=dog.id,
                position_x=1,
                position_y=0,
                is_visible=True,
            )
        )

        # Board B: Unplayable (1 symbol)
        board_unplayable = CommunicationBoard(
            user_id=user.id,
            name="Test: Unplayable Board",
            description="Should appear in disabled section",
            category="test",
            locale="en",
            is_language_learning=False,
        )
        session.add(board_unplayable)
        session.flush()

        session.add(
            BoardSymbol(
                board_id=board_unplayable.id,
                symbol_id=apple.id,
                position_x=0,
                position_y=0,
                is_visible=True,
            )
        )

        # Board C: Lang Normal (English -> Spanish target)
        board_lang_normal = CommunicationBoard(
            user_id=user.id,
            name="Test: Lang Normal",
            description="Should translate to Spanish",
            category="test",
            locale="en",
            is_language_learning=False,
        )
        session.add(board_lang_normal)
        session.flush()

        # Use custom text to verify it translates
        session.add(
            BoardSymbol(
                board_id=board_lang_normal.id,
                symbol_id=apple.id,
                custom_text="Red Apple",
                position_x=0,
                position_y=0,
                is_visible=True,
            )
        )

        # Board D: Lang Learning (English -> English target)
        board_lang_learning = CommunicationBoard(
            user_id=user.id,
            name="Test: Lang Learning",
            description="Should STAY English",
            category="test",
            locale="en",
            is_language_learning=True,  # KEY FLAG
        )
        session.add(board_lang_learning)
        session.flush()

        session.add(
            BoardSymbol(
                board_id=board_lang_learning.id,
                symbol_id=apple.id,
                custom_text="Red Apple",
                position_x=0,
                position_y=0,
                is_visible=True,
            )
        )

        session.commit()
        print("Test boards created successfully.")

    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    setup_test_data()
