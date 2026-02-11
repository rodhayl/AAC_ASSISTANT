"""
Migration script to add order_index column to symbols table.
Run this once to update existing databases.
"""

from loguru import logger
from sqlalchemy import text

from src.aac_app.models.database import create_engine_instance


def migrate_add_order_index():
    """Add order_index column to symbols table if it doesn't exist."""
    engine = create_engine_instance()

    try:
        with engine.connect() as conn:
            # Check if column exists
            result = conn.execute(text("PRAGMA table_info(symbols)"))
            columns = [row[1] for row in result.fetchall()]

            if "order_index" not in columns:
                logger.info("Adding order_index column to symbols table...")
                conn.execute(
                    text("ALTER TABLE symbols ADD COLUMN order_index INTEGER DEFAULT 0")
                )
                conn.commit()
                logger.info("Successfully added order_index column")
            else:
                logger.info("order_index column already exists, skipping migration")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    migrate_add_order_index()
    logger.info("Migration completed")
