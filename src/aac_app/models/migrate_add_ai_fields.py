"""
Migration script to add AI configuration fields to communication_boards table
"""

import sqlite3
from pathlib import Path


def migrate():
    # Database path
    db_path = Path(__file__).parent.parent.parent.parent / "data" / "aac_assistant.db"

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(communication_boards)")
        columns = [col[1] for col in cursor.fetchall()]

        migrations_needed = []

        if "ai_enabled" not in columns:
            migrations_needed.append(
                "ALTER TABLE communication_boards ADD COLUMN ai_enabled BOOLEAN DEFAULT 0"
            )

        if "ai_provider" not in columns:
            migrations_needed.append(
                "ALTER TABLE communication_boards ADD COLUMN ai_provider VARCHAR(50)"
            )

        if "ai_model" not in columns:
            migrations_needed.append(
                "ALTER TABLE communication_boards ADD COLUMN ai_model VARCHAR(100)"
            )

        if not migrations_needed:
            print("[OK] All AI columns already exist. No migration needed.")
            return

        # Execute migrations
        for migration in migrations_needed:
            print(f"Executing: {migration}")
            cursor.execute(migration)

        conn.commit()
        print(
            f"[OK] Successfully added {len(migrations_needed)} columns to communication_boards table"
        )

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
