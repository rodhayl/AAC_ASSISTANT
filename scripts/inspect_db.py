import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Make direct execution work from the repository root:
# ``uv run python scripts/inspect_db.py``.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DATABASE_PATH  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "database",
    nargs="?",
    type=Path,
    default=DATABASE_PATH,
    help="database path (default: configured data/aac_assistant.db)",
)
DB_PATH = parser.parse_args().database.resolve()

print(f"Inspecting database: {DB_PATH}")

if not os.path.exists(DB_PATH):
    print("Database file does not exist!")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    tables = ["users", "symbols", "achievements", "user_achievements", "communication_boards", "board_symbols"]
    for table in tables:
        try:
            cursor.execute(f"SELECT count(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"Table '{table}': {count} rows")

            if count > 0 and table == "users":
                cursor.execute("SELECT id, username, user_type FROM users")
                print("Users:", cursor.fetchall())

        except sqlite3.OperationalError as e:
            print(f"Table '{table}' error: {e}")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
