from loguru import logger
from sqlalchemy import inspect, text

from src.aac_app.models.database import get_session


def migrate_add_accessibility():
    """
    Add accessibility columns to user_settings table if they don't exist.
    """
    with get_session() as db:
        inspector = inspect(db.get_bind())
        columns = [c["name"] for c in inspector.get_columns("user_settings")]

        try:
            if "dwell_time" not in columns:
                logger.info("Adding dwell_time column to user_settings")
                db.execute(
                    text(
                        "ALTER TABLE user_settings ADD COLUMN dwell_time INTEGER DEFAULT 0"
                    )
                )

            if "ignore_repeats" not in columns:
                logger.info("Adding ignore_repeats column to user_settings")
                db.execute(
                    text(
                        "ALTER TABLE user_settings ADD COLUMN ignore_repeats INTEGER DEFAULT 0"
                    )
                )

            if "high_contrast" not in columns:
                logger.info("Adding high_contrast column to user_settings")
                db.execute(
                    text(
                        "ALTER TABLE user_settings ADD COLUMN high_contrast BOOLEAN DEFAULT 0"
                    )
                )

            db.commit()
            logger.info("Accessibility migration completed successfully")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            db.rollback()
            raise e


if __name__ == "__main__":
    migrate_add_accessibility()
