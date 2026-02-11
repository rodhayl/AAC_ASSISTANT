import sqlite3
import os

import sys

# Default path relative to script
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "aac_assistant.db")

def migrate(db_path=None):
    target_db = db_path or DEFAULT_DB_PATH
    print(f"Migrating database at {target_db}")
    if not os.path.exists(target_db):
        print(f"Database not found at {target_db}")
        return

    conn = sqlite3.connect(target_db)
    cursor = conn.cursor()

    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(achievements)")
        columns = [info[1] for info in cursor.fetchall()]
        print(f"Current columns: {columns}")

        if "created_by" not in columns:
            print("Adding created_by...")
            cursor.execute("ALTER TABLE achievements ADD COLUMN created_by INTEGER REFERENCES users(id)")
        else:
            print("created_by already exists")
        
        if "target_user_id" not in columns:
            print("Adding target_user_id...")
            cursor.execute("ALTER TABLE achievements ADD COLUMN target_user_id INTEGER REFERENCES users(id)")
        else:
            print("target_user_id already exists")

        if "is_manual" not in columns:
            print("Adding is_manual...")
            cursor.execute("ALTER TABLE achievements ADD COLUMN is_manual BOOLEAN DEFAULT 0")
        else:
            print("is_manual already exists")

        conn.commit()
        print("Migration complete!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    migrate(db_path)
