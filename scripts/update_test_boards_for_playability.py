import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aac_app.models.database import BoardSymbol, CommunicationBoard, Symbol  # noqa: E402


def update_boards():
    print("Updating test boards for playability...")

    engine = create_engine(
        f"sqlite:///{os.path.join(os.getcwd(), 'data', 'aac_assistant.db')}"
    )
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get Dog symbol
        dog = session.query(Symbol).filter_by(label="Dog").first()
        if not dog:
            print("Error: Dog symbol not found")
            return

        # Update Lang Normal Board
        boards_normal = (
            session.query(CommunicationBoard).filter_by(name="Test: Lang Normal").all()
        )
        for board in boards_normal:
            count = session.query(BoardSymbol).filter_by(board_id=board.id).count()
            if count < 2:
                print(f"Adding symbol to {board.name}...")
                session.add(
                    BoardSymbol(
                        board_id=board.id,
                        symbol_id=dog.id,
                        position_x=1,
                        position_y=0,
                        is_visible=True,
                    )
                )

        # Update Lang Learning Board
        boards_learning = (
            session.query(CommunicationBoard)
            .filter_by(name="Test: Lang Learning")
            .all()
        )
        for board in boards_learning:
            count = session.query(BoardSymbol).filter_by(board_id=board.id).count()
            if count < 2:
                print(f"Adding symbol to {board.name}...")
                session.add(
                    BoardSymbol(
                        board_id=board.id,
                        symbol_id=dog.id,
                        position_x=1,
                        position_y=0,
                        is_visible=True,
                    )
                )

        session.commit()
        print("Boards updated successfully.")

    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    update_boards()
