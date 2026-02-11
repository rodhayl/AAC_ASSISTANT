"""
Migration script to add language settings to communication_boards table.
"""

from loguru import logger
from sqlalchemy import text

from src.aac_app.models.database import create_engine_instance


def migrate_add_board_language_settings():
    """Add locale and is_language_learning columns to communication_boards table."""
    engine = create_engine_instance()

    try:
        with engine.connect() as conn:
            # Check existing columns
            result = conn.execute(text("PRAGMA table_info(communication_boards)"))
            columns = [row[1] for row in result.fetchall()]

            if "locale" not in columns:
                logger.info("Adding locale column to communication_boards...")
                conn.execute(
                    text(
                        "ALTER TABLE communication_boards ADD COLUMN locale VARCHAR(10) DEFAULT 'en'"
                    )
                )

            if "is_language_learning" not in columns:
                logger.info(
                    "Adding is_language_learning column to communication_boards..."
                )
                conn.execute(
                    text(
                        "ALTER TABLE communication_boards ADD COLUMN is_language_learning BOOLEAN DEFAULT 0"
                    )
                )

            conn.commit()
            logger.info("Migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    migrate_add_board_language_settings()
