from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.aac_app.models.database import BoardSymbol, CommunicationBoard, Symbol
from src.config import DATABASE_PATH

engine = create_engine(f"sqlite:///{DATABASE_PATH}")
Session = sessionmaker(bind=engine)
session = Session()

# Find the horse symbol on Student Flow Board (ID 8)
board_id = 8
symbol_label = "horse"

board = (
    session.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
)
if not board:
    print(f"Board {board_id} not found")
    exit(1)

print(f"Board: {board.name} (ID: {board.id})")

# Find the symbol
# We need to join with Symbol table to filter by label
board_symbol = (
    session.query(BoardSymbol)
    .join(Symbol)
    .filter(BoardSymbol.board_id == board_id, Symbol.label == symbol_label)
    .first()
)

if board_symbol:
    print(f"Symbol: {board_symbol.symbol.label}")
    print(f"BoardSymbol ID: {board_symbol.id}")
    print(f"Linked Board ID: {board_symbol.linked_board_id}")
else:
    print(f"Symbol '{symbol_label}' not found on board {board_id}")

session.close()
