from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src import config


def migrate_add_ui_language():
    """Add ui_language column to user_settings if missing (idempotent)."""
    db_path = config.DATABASE_PATH
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    with Session(engine) as session:
        try:
            cols = session.execute(text("PRAGMA table_info(user_settings)")).all()
            names = [c[1] for c in cols]
            if "ui_language" not in names:
                session.execute(
                    text(
                        "ALTER TABLE user_settings ADD COLUMN ui_language TEXT DEFAULT 'es-ES'"
                    )
                )
                session.commit()
                logger.info("Added ui_language column to user_settings")
            else:
                logger.debug("ui_language column already exists")
        except Exception as e:
            logger.error(f"Failed to migrate ui_language: {e}")


if __name__ == "__main__":
    migrate_add_ui_language()
