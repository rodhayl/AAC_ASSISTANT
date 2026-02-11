from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.aac_app.models.database import CommunicationBoard

# Database setup
DATABASE_URL = "sqlite:///./aac_app.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def list_boards():
    db = SessionLocal()
    try:
        boards = db.query(CommunicationBoard).all()
        for board in boards:
            print(f"ID: {board.id}, Name: {board.name}")
    finally:
        db.close()


if __name__ == "__main__":
    list_boards()
