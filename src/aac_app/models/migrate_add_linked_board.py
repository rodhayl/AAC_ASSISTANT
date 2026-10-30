import os
import sys

from sqlalchemy import create_engine, text

# Add the project root to the python path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))

from src.config import DATABASE_PATH  # noqa: E402


def get_db_url():
    return f"sqlite:///{DATABASE_PATH}"


def migrate():
    """
    Add linked_board_id and color columns to board_symbols table
    """
    database_url = get_db_url()
    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check if columns exist first to avoid errors on re-run
        # SQLite doesn't support IF NOT EXISTS in ALTER TABLE well, so we check pragmas or just try/except

        print("Migrating database...")

        try:
            conn.execute(text("ALTER TABLE board_symbols ADD COLUMN color VARCHAR(20)"))
            print("Added color column")
        except Exception as e:
            print(f"Color column might already exist or error: {e}")

        try:
            conn.execute(
                text(
                    "ALTER TABLE board_symbols ADD COLUMN linked_board_id INTEGER REFERENCES communication_boards(id)"
                )
            )
            print("Added linked_board_id column")
        except Exception as e:
            print(f"linked_board_id column might already exist or error: {e}")

        conn.commit()
        print("Migration completed successfully.")


if __name__ == "__main__":
    migrate()
