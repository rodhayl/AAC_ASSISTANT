import sys
import os

# Add root to path so src can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.config import DATABASE_PATH

def find_board(name):
    engine = create_engine(f"sqlite:///{DATABASE_PATH}")
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Use raw SQL for simplicity if models are complex to import or just use SQL alchemy
        result = session.execute(text("SELECT id, name, description FROM communication_boards WHERE name LIKE :name"), {"name": f"%{name}%"})
        boards = result.fetchall()
        if boards:
            print(f"Found {len(boards)} boards matching '{name}':")
            for b in boards:
                print(f"ID: {b.id}, Name: {b.name}, Description: {b.description}")
        else:
            print(f"No boards found matching '{name}'")
    finally:
        session.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        find_board(sys.argv[1])
    else:
        print("Usage: python find_board.py <name>")
