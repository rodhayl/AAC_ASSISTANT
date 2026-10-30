"""
Migration script to add student_teachers table.
Run this once to update existing databases.
"""

from loguru import logger
from sqlalchemy import text

from src.aac_app.models.database import create_engine_instance


def migrate_add_student_teachers():
    """Add student_teachers table if it doesn't exist."""
    engine = create_engine_instance()

    try:
        with engine.connect() as conn:
            # Check if table exists
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='student_teachers'"
                )
            )
            table_exists = result.fetchone()

            if not table_exists:
                logger.info("Creating student_teachers table...")
                conn.execute(
                    text(
                        """
                    CREATE TABLE student_teachers (
                        id INTEGER PRIMARY KEY,
                        student_id INTEGER NOT NULL,
                        teacher_id INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(student_id) REFERENCES users(id),
                        FOREIGN KEY(teacher_id) REFERENCES users(id)
                    )
                """
                    )
                )
                conn.commit()
                logger.info("Successfully created student_teachers table")
            else:
                logger.info("student_teachers table already exists, skipping migration")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    migrate_add_student_teachers()
    logger.info("Migration completed")
