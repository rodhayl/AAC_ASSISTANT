"""Idempotent seed data for first-run and demo environments."""

from __future__ import annotations

import os
import secrets

from loguru import logger
from sqlalchemy.orm import Session

from src import config
from src.aac_app import schema
from src.aac_app.db import get_session
from src.aac_app.models import (
    Achievement,
    BoardAssignment,
    BoardSymbol,
    CommunicationBoard,
    LearningMode,
    Symbol,
    User,
    UserAchievement,
)
from src.aac_app.services.achievement_catalog import (
    INITIAL_ACHIEVEMENT_KEYS,
    PREDEFINED_ACHIEVEMENTS,
)
from src.aac_app.services.auth_service import password_strength_error
from src.aac_app.services.credential_service import mark_credentials_changed

DEFAULT_COMMUNICATION_BOARD_NAME = "Comunicación General"
LEGACY_COMMUNICATION_BOARD_NAME = "General Communication"


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
        _create_default_learning_modes(session)
        _ensure_bootstrap_admin(session)
        _rename_legacy_default_board(session)

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


def _ensure_bootstrap_admin(session: Session) -> None:
    """Create or repair the configured first-run administrator."""
    if not config.get_bool("AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN", True):
        return

    username = config.get("AAC_BOOTSTRAP_ADMIN_USERNAME", "admin1").strip() or "admin1"
    if session.query(User).filter(User.user_type == "admin").first():
        return

    explicit_password = config.explicit_bootstrap_password()
    if config.ENVIRONMENT.strip().casefold() == "production":
        # Production must never fall back to a generated credential or the
        # insecure development default: a unique password is mandatory.
        if explicit_password is None:
            raise ValueError(
                "AAC_BOOTSTRAP_ADMIN_PASSWORD is not acceptable in production: "
                "a unique password must be configured"
            )
        password = explicit_password
        error = password_strength_error(password)
        if password == config.DEFAULT_BOOTSTRAP_ADMIN_PASSWORD:
            error = "the development default must be changed"
        if error:
            raise ValueError(
                "AAC_BOOTSTRAP_ADMIN_PASSWORD is not acceptable in production: "
                + error
            )
    else:
        password = config.resolve_bootstrap_password()
        if password is None:
            logger.info(
                "No administrator account configured. Complete initial setup via "
                "the web setup screen (/setup) or configure AAC_BOOTSTRAP_ADMIN_PASSWORD."
            )
            return

    from src.aac_app.services.auth_service import get_password_hash

    user = session.query(User).filter(User.username == username).first()
    if user:
        user.user_type = "admin"
        user.is_active = True
        user.password_hash = get_password_hash(password)
        mark_credentials_changed(user)
        if not user.display_name:
            user.display_name = "Administrator"
    else:
        session.add(
            User(
                username=username,
                display_name="Administrator",
                user_type="admin",
                password_hash=get_password_hash(password),
                is_active=True,
            )
        )
    session.flush()


def _rename_legacy_default_board(session: Session) -> None:
    """Rename only the untouched legacy demo template, once."""
    admin = session.query(User).filter(User.username == "admin1").first()
    if admin is None:
        return
    board = (
        session.query(CommunicationBoard)
        .filter(
            CommunicationBoard.user_id == admin.id,
            CommunicationBoard.name == LEGACY_COMMUNICATION_BOARD_NAME,
            CommunicationBoard.is_template.is_(True),
        )
        .first()
    )
    if board is not None:
        board.name = DEFAULT_COMMUNICATION_BOARD_NAME
        logger.info("Renamed legacy demo board to {}", DEFAULT_COMMUNICATION_BOARD_NAME)


def _create_sample_boards(session: Session) -> None:
    """Create the demo communication board and its student assignment."""
    admin = session.query(User).filter(User.username == "admin1").first()
    if not admin:
        admin = session.query(User).first()
    if not admin:
        return

    board = (
        session.query(CommunicationBoard)
        .filter(
            CommunicationBoard.user_id == admin.id,
            CommunicationBoard.name == DEFAULT_COMMUNICATION_BOARD_NAME,
        )
        .first()
    )
    if board is None:
        # Migrate only the untouched demo board created by older versions.
        # A user-created board that was renamed must never be overwritten.
        board = (
            session.query(CommunicationBoard)
            .filter(
                CommunicationBoard.user_id == admin.id,
                CommunicationBoard.name == LEGACY_COMMUNICATION_BOARD_NAME,
                CommunicationBoard.is_template.is_(True),
            )
            .first()
        )
        if board is not None:
            board.name = DEFAULT_COMMUNICATION_BOARD_NAME
    if board is None:
        board = CommunicationBoard(
            name=DEFAULT_COMMUNICATION_BOARD_NAME,
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

        # The demo board contains at most 12 symbols; do not scan the full
        # catalog when a large production symbol library is present. The 12
        # seeded sample symbols fill the 3x4 grid so the board crosses the
        # 50% playability threshold instead of rendering as "Board Locked".
        for index, symbol in enumerate(
            session.query(Symbol).order_by(Symbol.id).limit(12)
        ):
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

    # Students only see assigned boards in the Communication view, so assign
    # the demo board to the demo student. Idempotent for existing installs.
    student = session.query(User).filter(User.username == "student1").first()
    if student is not None:
        existing = (
            session.query(BoardAssignment)
            .filter(
                BoardAssignment.board_id == board.id,
                BoardAssignment.student_id == student.id,
            )
            .first()
        )
        if existing is None:
            session.add(
                BoardAssignment(
                    board_id=board.id,
                    student_id=student.id,
                    assigned_by=admin.id,
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


DEFAULT_LEARNING_MODES = [
    {
        "key": "practice",
        "name": "Practice",
        "description": "Adaptive questions with feedback on every answer.",
        "prompt_instruction": "Ask short adaptive questions about the topic and give encouraging feedback after each answer.",
        "auto_ask_enabled": True,
    },
    {
        "key": "quiz",
        "name": "Quiz",
        "description": "Multiple-choice questions with a score at the end.",
        "prompt_instruction": "Run a quiz: ask multiple-choice questions one at a time, track correct answers, and summarise the score at the end.",
        "auto_ask_enabled": True,
    },
    {
        "key": "conversation",
        "name": "Conversation",
        "description": "Open-ended conversation practice without auto-generated questions.",
        "prompt_instruction": "Hold a natural conversation about the topic. Do not generate quiz-style questions; respond conversationally.",
        "auto_ask_enabled": False,
    },
    {
        "key": "roleplay",
        "name": "Roleplay",
        "description": "Practice by acting out a scenario with the AI.",
        "prompt_instruction": "Act out a roleplay scenario about the topic. Take one role and invite the student to take the other, staying in character.",
        "auto_ask_enabled": False,
    },
]


def _create_default_learning_modes(session: Session) -> None:
    """Seed the system learning modes when none exist (idempotent)."""
    existing = (
        session.query(LearningMode).filter(LearningMode.created_by.is_(None)).first()
    )
    if existing is not None:
        return
    for mode in DEFAULT_LEARNING_MODES:
        session.add(
            LearningMode(
                name=mode["name"],
                key=mode["key"],
                description=mode["description"],
                prompt_instruction=mode["prompt_instruction"],
                auto_ask_enabled=mode["auto_ask_enabled"],
                is_custom=False,
                created_by=None,
            )
        )
    logger.info("Seeded %d default learning modes", len(DEFAULT_LEARNING_MODES))


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
        {
            "label": "hello",
            "description": "A friendly greeting",
            "category": "social",
            "keywords": "hello, hi, greetings",
        },
        {
            "label": "goodbye",
            "description": "A parting word",
            "category": "social",
            "keywords": "goodbye, bye, leave",
        },
        {
            "label": "yes",
            "description": "Agreement or confirmation",
            "category": "social",
            "keywords": "yes, agree, correct",
        },
        {
            "label": "no",
            "description": "Disagreement or refusal",
            "category": "social",
            "keywords": "no, disagree, incorrect",
        },
        {
            "label": "please",
            "description": "A polite request word",
            "category": "social",
            "keywords": "please, polite",
        },
        {
            "label": "thank you",
            "description": "Expressing gratitude",
            "category": "social",
            "keywords": "thanks, gratitude, thank you",
        },
        {
            "label": "help",
            "description": "Asking for assistance",
            "category": "social",
            "keywords": "help, assist, support",
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
            field: PREDEFINED_ACHIEVEMENTS[key][field]
            for field in (
                "name",
                "description",
                "category",
                "criteria_type",
                "criteria_value",
                "points",
                "icon",
            )
        }
        for key in INITIAL_ACHIEVEMENT_KEYS
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
        system_matches = [match for match in matches if match.created_by is None]
        if not system_matches:
            session.add(Achievement(**values))
            continue

        # Older releases inserted the same system rows on every boot. Keep
        # the first system row as the stable definition and move any earned
        # records before removing duplicate system rows. Custom achievements
        # with the same definition are intentionally left untouched.
        canonical = system_matches[0]
        canonical.points = values["points"]
        canonical.icon = values["icon"]
        for duplicate in system_matches[1:]:
            session.query(UserAchievement).filter(
                UserAchievement.achievement_id == duplicate.id
            ).update(
                {"achievement_id": canonical.id},
                synchronize_session=False,
            )
            session.delete(duplicate)

    session.flush()
