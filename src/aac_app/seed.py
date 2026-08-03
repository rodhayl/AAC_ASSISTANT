"""Idempotent seed data for first-run and demo environments."""

from __future__ import annotations

import os
import secrets

from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app import schema
from src.aac_app.db import get_session
from src.aac_app.models import (
    Achievement,
    BoardSymbol,
    CommunicationBoard,
    Symbol,
    User,
    UserAchievement,
)


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment flag."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _seed_password_for(username: str) -> str:
    """Resolve a sample user password from environment variables."""
    per_user = os.environ.get(f"AAC_SEED_{username.upper()}_PASSWORD")
    if per_user:
        return per_user

    default_password = os.environ.get("AAC_SEED_DEFAULT_PASSWORD")
    if default_password:
        return default_password

    return secrets.token_urlsafe(18)


def init_database(*, ensure_schema: bool = True) -> None:
    """Seed missing system/demo data, optionally ensuring the schema first."""
    logger.info("Initializing database...")
    if ensure_schema:
        schema.ensure()

    with get_session() as session:
        _create_sample_symbols(session)
        _create_sample_achievements(session)

        if _env_flag("AAC_SEED_SAMPLE_DATA", default=False):
            _create_sample_users(session)
            _create_sample_boards(session)
            logger.warning(
                "Sample users/boards seeded because AAC_SEED_SAMPLE_DATA=true. "
                "Disable this flag for production."
            )
        else:
            logger.info(
                "Skipping sample users/boards seeding. "
                "Set AAC_SEED_SAMPLE_DATA=true for local demo data."
            )

    logger.info("Database initialized successfully")


def _create_sample_boards(session: Session) -> None:
    """Create the demo communication board when it is missing."""
    admin = session.query(User).filter(User.username == "admin1").first()
    if not admin:
        admin = session.query(User).first()
    if not admin:
        return

    board = (
        session.query(CommunicationBoard)
        .filter(
            CommunicationBoard.user_id == admin.id,
            CommunicationBoard.name == "General Communication",
        )
        .first()
    )
    if board:
        return

    board = CommunicationBoard(
        name="General Communication",
        description="Basic vocabulary board with common symbols",
        user_id=admin.id,
        is_public=True,
        is_template=True,
        grid_rows=3,
        grid_cols=4,
        ai_enabled=True,
        ai_provider="ollama",
    )
    session.add(board)
    session.flush()

    for index, symbol in enumerate(session.query(Symbol).order_by(Symbol.id)):
        if index >= 12:
            break
        session.add(
            BoardSymbol(
                board_id=board.id,
                symbol_id=symbol.id,
                position_x=index % 4,
                position_y=index // 4,
                is_visible=True,
            )
        )
    session.flush()


def _create_sample_users(session: Session) -> None:
    """Create missing demo users with non-hardcoded passwords."""
    from src.aac_app.services.auth_service import get_password_hash

    sample_users = [
        ("student1", "Alex", "student"),
        ("teacher1", "Ms. Johnson", "teacher"),
        ("admin1", "Admin", "admin"),
    ]

    for username, display_name, user_type in sample_users:
        if session.query(User).filter(User.username == username).first():
            continue
        session.add(
            User(
                username=username,
                display_name=display_name,
                user_type=user_type,
                password_hash=get_password_hash(_seed_password_for(username)),
            )
        )

    session.flush()


def _create_sample_symbols(session: Session) -> None:
    """Create the built-in communication symbols when they are missing."""
    sample_symbols = [
        {
            "label": "cow",
            "description": "A farm animal that gives milk",
            "category": "farm_animals",
            "keywords": "cow, farm, milk, animal",
        },
        {
            "label": "horse",
            "description": "A large animal you can ride",
            "category": "farm_animals",
            "keywords": "horse, farm, ride, animal",
        },
        {
            "label": "chicken",
            "description": "A bird that lays eggs",
            "category": "farm_animals",
            "keywords": "chicken, farm, eggs, bird",
        },
        {
            "label": "apple",
            "description": "A red fruit",
            "category": "food",
            "keywords": "apple, fruit, red, food",
        },
        {
            "label": "water",
            "description": "Clear liquid for drinking",
            "category": "drinks",
            "keywords": "water, drink, liquid",
        },
    ]

    for values in sample_symbols:
        existing = (
            session.query(Symbol)
            .filter(
                Symbol.label == values["label"],
                Symbol.category == values["category"],
            )
            .first()
        )
        if existing:
            continue
        session.add(Symbol(**values))

    session.flush()


def _create_sample_achievements(session: Session) -> None:
    """Create the three system achievements without duplicating them."""
    sample_achievements = [
        {
            "name": "First Steps",
            "description": "Complete your first learning session",
            "category": "beginner",
            "criteria_type": "sessions_completed",
            "criteria_value": 1,
        },
        {
            "name": "Vocabulary Explorer",
            "description": "Learn 10 new words",
            "category": "vocabulary",
            "criteria_type": "vocabulary_size",
            "criteria_value": 10,
        },
        {
            "name": "Quick Learner",
            "description": "Answer 5 questions correctly",
            "category": "performance",
            "criteria_type": "correct_answers",
            "criteria_value": 5,
        },
    ]

    for values in sample_achievements:
        matches = (
            session.query(Achievement)
            .filter(
                Achievement.name == values["name"],
                Achievement.description == values["description"],
                Achievement.category == values["category"],
                Achievement.criteria_type == values["criteria_type"],
                Achievement.criteria_value == values["criteria_value"],
            )
            .order_by(Achievement.id)
            .all()
        )
        if not matches:
            session.add(Achievement(**values))
            continue

        # Older releases inserted the same system rows on every boot. Keep
        # the first row as the stable definition and move any earned records
        # before removing duplicate seed rows.
        canonical = matches[0]
        for duplicate in matches[1:]:
            session.query(UserAchievement).filter(
                UserAchievement.achievement_id == duplicate.id
            ).update(
                {"achievement_id": canonical.id},
                synchronize_session=False,
            )
            session.delete(duplicate)

    session.flush()
