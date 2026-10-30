import os
import secrets
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Float,
    Boolean,
    ForeignKey,
    JSON,
    func,
    text,
)
from sqlalchemy.orm import sessionmaker, relationship, Session, declarative_base
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from typing import Generator
from loguru import logger

# Create base class for all models
Base = declarative_base()

# One-time runtime schema upgrades for older SQLite DBs.
_schema_checked = False
_engine_instance = None
_engine_url = None

# Import audit models after Base is created to avoid circular imports
# These models use the same Base and will be included in create_all()
try:
    from src.aac_app.models.audit_log import AuditLog, FailedLoginAttempt
except ImportError:
    # Models not yet created, will be imported later
    pass

class User(Base):
    """User model for authentication and profiles"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)  # Required for authentication
    display_name = Column(String(100), nullable=False)
    user_type = Column(String(20), default='student')  # student, teacher, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    learning_sessions = relationship("LearningSession", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")
    communication_boards = relationship("CommunicationBoard", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False)

class UserSettings(Base):
    """User-specific settings and preferences"""
    __tablename__ = 'user_settings'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)

    # TTS Settings
    tts_voice = Column(String(20), default='default')  # default, female, male
    tts_language = Column(String(10), default='en')  # en, es, etc.

    # UI Preferences
    ui_language = Column(String(10), default='es-ES')  # e.g., 'en-US', 'es-ES'
    notifications_enabled = Column(Boolean, default=True)
    voice_mode_enabled = Column(Boolean, default=True)
    dark_mode = Column(Boolean, default=False)
    dwell_time = Column(Integer, default=0)  # ms
    ignore_repeats = Column(Integer, default=0)  # ms
    high_contrast = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="settings")

class StudentTeacher(Base):
    """Association between students and teachers"""
    __tablename__ = 'student_teachers'

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    teacher_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    student = relationship("User", foreign_keys=[student_id], backref="teachers")
    teacher = relationship("User", foreign_keys=[teacher_id], backref="students")

class CommunicationBoard(Base):
    """AAC communication boards"""
    __tablename__ = 'communication_boards'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), default='general')
    is_public = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    grid_rows = Column(Integer, default=4)
    grid_cols = Column(Integer, default=5)
    locale = Column(String(10), default='en')  # Board language/locale
    is_language_learning = Column(Boolean, default=False)  # Language learning mode

    # AI Configuration
    ai_enabled = Column(Boolean, default=False)
    ai_provider = Column(String(50), nullable=True)  # 'ollama', 'openrouter', or None
    ai_model = Column(String(100), nullable=True)

    # Relationships
    user = relationship("User", back_populates="communication_boards")
    symbols = relationship("BoardSymbol", back_populates="board", foreign_keys="[BoardSymbol.board_id]")

class Symbol(Base):
    """AAC symbols/pictograms"""
    __tablename__ = 'symbols'

    id = Column(Integer, primary_key=True)
    label = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), default='general')
    image_path = Column(String(255))
    audio_path = Column(String(255))
    keywords = Column(Text)  # Comma-separated keywords for search
    language = Column(String(10), default='en')
    is_builtin = Column(Boolean, default=False)
    order_index = Column(Integer, default=0)  # Global library ordering
    created_at = Column(DateTime, default=func.now())

    # Relationships
    board_symbols = relationship("BoardSymbol", back_populates="symbol")

class BoardSymbol(Base):
    """Many-to-many relationship between boards and symbols"""
    __tablename__ = 'board_symbols'
    
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey('communication_boards.id'), nullable=False)
    symbol_id = Column(Integer, ForeignKey('symbols.id'), nullable=False)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    size = Column(Integer, default=1)  # Size multiplier
    is_visible = Column(Boolean, default=True)
    custom_text = Column(String(100))  # Override default symbol text
    linked_board_id = Column(Integer, ForeignKey('communication_boards.id'), nullable=True)  # Navigation to another board
    color = Column(String(20), nullable=True)  # Symbol background color
    order_index = Column(Integer, default=0)  # Order within board
    
    # Relationships
    board = relationship("CommunicationBoard", foreign_keys=[board_id], back_populates="symbols")
    symbol = relationship("Symbol", back_populates="board_symbols")
    linked_board = relationship("CommunicationBoard", foreign_keys=[linked_board_id])

class BoardAssignment(Base):
    __tablename__ = 'board_assignments'
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey('communication_boards.id'), nullable=False)
    student_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    assigned_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=func.now())

class LearningSession(Base):
    """AI tutoring sessions"""
    __tablename__ = 'learning_sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    topic_name = Column(String(100), nullable=False)
    purpose = Column(Text)
    status = Column(String(20), default='active')  # active, completed, paused
    comprehension_score = Column(Float, default=0.0)
    questions_asked = Column(Integer, default=0)
    questions_answered = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    conversation_history = Column(JSON, default=list)
    started_at = Column(DateTime, default=func.now())
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="learning_sessions")

class LearningMode(Base):
    """DeepSeek/Learning Companion interaction modes"""
    __tablename__ = 'learning_modes'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    key = Column(String(50), nullable=False)  # Unique identifier (e.g., 'socratic', 'roleplay')
    description = Column(Text)
    prompt_instruction = Column(Text)  # The actual system prompt instructions
    is_custom = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)  # Null = System Default
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User")

class Achievement(Base):
    """Achievement definitions"""
    __tablename__ = 'achievements'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(50))
    category = Column(String(50), default='general')
    points = Column(Integer, default=10)
    criteria_type = Column(String(50))  # sessions_completed, correct_answers, etc.
    criteria_value = Column(Float)  # Threshold value
    is_active = Column(Boolean, default=True)
    is_manual = Column(Boolean, default=False)  # Custom achievement manually created
    
    # Custom achievement targeting
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)  # Null = System
    target_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # Null = All users

    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    user_achievements = relationship("UserAchievement", back_populates="achievement", foreign_keys="UserAchievement.achievement_id")
    creator = relationship("User", foreign_keys=[created_by])
    target_user = relationship("User", foreign_keys=[target_user_id])

class UserAchievement(Base):
    """User-earned achievements"""
    __tablename__ = 'user_achievements'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    achievement_id = Column(Integer, ForeignKey('achievements.id'), nullable=False)
    earned_at = Column(DateTime, default=func.now())
    progress = Column(Float, default=1.0)  # Progress towards achievement (0.0-1.0)
    
    # Relationships
    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="user_achievements")

class LearningPlan(Base):
    """Structured learning plans"""
    __tablename__ = 'learning_plans'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    difficulty = Column(String(20), default='beginner')  # beginner, intermediate, advanced
    status = Column(String(20), default='active')  # active, completed, archived
    target_completion = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User")
    tasks = relationship("LearningTask", back_populates="plan")

class LearningTask(Base):
    """Individual tasks within learning plans"""
    __tablename__ = 'learning_tasks'
    
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey('learning_plans.id'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    task_type = Column(String(50), default='practice')  # practice, assessment, review
    status = Column(String(20), default='pending')  # pending, in_progress, completed
    priority = Column(Integer, default=1)  # 1-5, higher is more important
    estimated_duration = Column(Integer, default=30)  # minutes
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    plan = relationship("LearningPlan", back_populates="tasks")

class UserProgress(Base):
    """Track user learning progress"""
    __tablename__ = 'user_progress'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    metric_type = Column(String(50), nullable=False)  # vocabulary_size, comprehension_score, etc.
    metric_value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User")

class CollaborationSession(Base):
    """Collaboration sessions for real-time communication"""
    __tablename__ = 'collaboration_sessions'
    
    id = Column(Integer, primary_key=True)
    session_name = Column(String(100), nullable=False)
    host_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    status = Column(String(20), default='waiting')  # waiting, active, completed
    session_code = Column(String(20), unique=True, nullable=False)
    max_participants = Column(Integer, default=5)
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

class AppSettings(Base):
    """Global application settings (admin-only configuration)"""
    __tablename__ = 'app_settings'

    id = Column(Integer, primary_key=True)
    setting_key = Column(String(50), unique=True, nullable=False)
    setting_value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=True)

class Notification(Base):
    """Persistent notifications for users"""
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(20), default='info')  # info, success, warning, error
    priority = Column(String(20), default='normal')  # low, normal, high
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    read_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User")

class SymbolUsageLog(Base):
    """Track symbol usage for analytics and personalization"""
    __tablename__ = 'symbol_usage_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    session_id = Column(Integer, ForeignKey('learning_sessions.id'), nullable=True)
    symbol_id = Column(Integer, ForeignKey('symbols.id'), nullable=True)
    symbol_label = Column(String(50), nullable=False)  # Store label for deleted symbols
    symbol_category = Column(String(50), nullable=True)
    position_in_utterance = Column(Integer, nullable=False)  # 0-indexed position
    utterance_length = Column(Integer, nullable=False)  # Total symbols in utterance
    semantic_intent = Column(String(20), nullable=True)  # REQUEST, QUESTION, etc.
    timestamp = Column(DateTime, default=func.now(), nullable=False)
    
    # Optional context
    context_topic = Column(String(100), nullable=True)  # Learning session topic
    
    # Relationships
    user = relationship("User")
    session = relationship("LearningSession")
    symbol = relationship("Symbol")


class GuardianProfile(Base):
    """
    Hidden profile for Learning Companion personality configuration.
    Only visible to teachers and admins - never exposed to students.
    Combines template-based defaults with per-student customization.
    """
    __tablename__ = 'guardian_profiles'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)

    # Template Selection (from YAML templates)
    template_name = Column(String(100), default='default')  # e.g., 'autism_friendly', 'preschool'

    # Demographics (can be null if unknown/not applicable)
    age = Column(Integer, nullable=True)
    gender = Column(String(30), nullable=True)  # male, female, non-binary, prefer-not-to-say, other

    # Medical/Accessibility Context (JSON for flexibility)
    # Structure: {"diagnoses": [], "sensitivities": [], "accessibility_needs": [], "notes": ""}
    medical_context = Column(JSON, default=dict)

    # Communication Style Overrides (overrides template defaults)
    # Structure: {"tone": "encouraging", "complexity": "simple", "sentence_length": "short", ...}
    communication_style = Column(JSON, default=dict)

    # Safety Constraints (merged with template constraints)
    # Structure: {"forbidden_topics": [], "trigger_words": [], "content_filter_level": "strict"}
    safety_constraints = Column(JSON, default=dict)

    # Companion Persona Customization
    # Structure: {"name": "Alex", "role": "friendly tutor", "personality": ["patient", "encouraging"]}
    companion_persona = Column(JSON, default=dict)

    # Free-form custom instructions (appended to template instructions)
    custom_instructions = Column(Text, nullable=True)

    # Confidential notes (NEVER sent to LLM - for teacher reference only)
    private_notes = Column(Text, nullable=True)

    # Profile status
    is_active = Column(Boolean, default=True)

    # Audit trail
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="guardian_profile")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class GuardianProfileHistory(Base):
    """
    Audit log for guardian profile changes.
    Tracks who changed what and when for compliance.
    """
    __tablename__ = 'guardian_profile_history'

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey('guardian_profiles.id'), nullable=False)
    
    # What changed
    field_name = Column(String(50), nullable=False)  # e.g., 'template_name', 'safety_constraints'
    old_value = Column(Text, nullable=True)  # JSON-serialized previous value
    new_value = Column(Text, nullable=True)  # JSON-serialized new value
    
    # Who and when
    changed_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    changed_at = Column(DateTime, default=func.now())
    
    # Optional reason for change
    change_reason = Column(Text, nullable=True)

    # Relationships
    profile = relationship("GuardianProfile")
    changer = relationship("User")

# Database setup functions
def get_database_path() -> str:
    """Get the path to the SQLite database file"""
    from src import config
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(config.DATABASE_PATH)

def create_engine_instance():
    """Create SQLAlchemy engine instance"""
    global _schema_checked, _engine_instance, _engine_url
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        target_url = database_url
    else:
        db_path = get_database_path()
        target_url = f"sqlite:///{db_path}"

    if _engine_instance is not None and _engine_url == target_url:
        return _engine_instance

    if _engine_url != target_url:
        _schema_checked = False

    logger.info(f"Creating database engine: {target_url}")
    connect_args = {"check_same_thread": False} if target_url.startswith("sqlite") else {}
    engine_kwargs = {}
    if target_url in {"sqlite:///:memory:", "sqlite://"}:
        # Keep one shared in-memory DB connection for tests.
        engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(
        target_url,
        echo=False,
        connect_args=connect_args,
        **engine_kwargs,
    )

    if not _schema_checked:
        try:
            _ensure_sqlite_schema(engine)
        finally:
            _schema_checked = True

    _engine_instance = engine
    _engine_url = target_url

    return engine


def _ensure_sqlite_schema(engine) -> None:
    """
    Ensure required columns exist in SQLite databases created before newer schema changes.
    This keeps packaged builds working when shipping an older `aac_assistant.db`.
    """
    with engine.connect() as conn:
        def table_exists(table: str) -> bool:
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table},
            ).fetchone()
            return row is not None

        def has_column(table: str, column: str) -> bool:
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            cols = [row[1] for row in result.fetchall()]
            return column in cols

        # Symbols: global ordering
        if table_exists("symbols") and not has_column("symbols", "order_index"):
            logger.info("DB upgrade: adding symbols.order_index")
            conn.execute(text("ALTER TABLE symbols ADD COLUMN order_index INTEGER DEFAULT 0"))

        # BoardSymbols: per-board ordering
        if table_exists("board_symbols") and not has_column("board_symbols", "order_index"):
            logger.info("DB upgrade: adding board_symbols.order_index")
            conn.execute(text("ALTER TABLE board_symbols ADD COLUMN order_index INTEGER DEFAULT 0"))

        # UserSettings: preferences fields added after initial schema
        if table_exists("user_settings") and not has_column("user_settings", "ui_language"):
            logger.info("DB upgrade: adding user_settings.ui_language")
            conn.execute(text("ALTER TABLE user_settings ADD COLUMN ui_language TEXT DEFAULT 'es-ES'"))

        if table_exists("user_settings") and not has_column("user_settings", "voice_mode_enabled"):
            logger.info("DB upgrade: adding user_settings.voice_mode_enabled")
            conn.execute(text("ALTER TABLE user_settings ADD COLUMN voice_mode_enabled INTEGER DEFAULT 1"))

        if table_exists("user_settings") and not has_column("user_settings", "dwell_time"):
            logger.info("DB upgrade: adding user_settings.dwell_time")
            conn.execute(text("ALTER TABLE user_settings ADD COLUMN dwell_time INTEGER DEFAULT 0"))

        if table_exists("user_settings") and not has_column("user_settings", "ignore_repeats"):
            logger.info("DB upgrade: adding user_settings.ignore_repeats")
            conn.execute(text("ALTER TABLE user_settings ADD COLUMN ignore_repeats INTEGER DEFAULT 0"))

        if table_exists("user_settings") and not has_column("user_settings", "high_contrast"):
            logger.info("DB upgrade: adding user_settings.high_contrast")
            conn.execute(text("ALTER TABLE user_settings ADD COLUMN high_contrast INTEGER DEFAULT 0"))

        # Learning modes: keep packaged DBs compatible with newer ORM models
        if table_exists("learning_modes") and not has_column("learning_modes", "updated_at"):
            logger.info("DB upgrade: adding learning_modes.updated_at")
            # SQLite only allows ADD COLUMN defaults that are constant literals.
            # Keep it nullable and backfill from created_at to avoid breaking older DBs.
            conn.execute(text("ALTER TABLE learning_modes ADD COLUMN updated_at DATETIME"))
            conn.execute(text("UPDATE learning_modes SET updated_at = created_at WHERE updated_at IS NULL"))

        conn.commit()

def create_session_factory():
    """Create session factory"""
    engine = create_engine_instance()
    return sessionmaker(bind=engine, expire_on_commit=False)

def create_tables():
    """Create all database tables"""
    engine = create_engine_instance()
    logger.info("Creating database tables...")
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully")

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get database session (context manager)"""
    SessionLocal = create_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment flag."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _seed_password_for(username: str) -> str:
    """
    Resolve a sample user password from env vars.

    Priority:
    1) AAC_SEED_<USERNAME>_PASSWORD
    2) AAC_SEED_DEFAULT_PASSWORD
    3) Random one-time generated password
    """
    per_user = os.environ.get(f"AAC_SEED_{username.upper()}_PASSWORD")
    if per_user:
        return per_user

    default_password = os.environ.get("AAC_SEED_DEFAULT_PASSWORD")
    if default_password:
        return default_password

    return secrets.token_urlsafe(18)


def init_database():
    """Initialize the database with tables and optional sample data."""
    logger.info("Initializing database...")

    create_tables()

    with get_session() as session:
        if session.query(User).first():
            logger.info("Database already initialized with data")
            return

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

        session.commit()
        logger.info("Database initialized successfully")


def _create_sample_boards(session):
    """Create sample communication boards."""
    admin = session.query(User).filter(User.username == "admin1").first()
    if not admin:
        admin = session.query(User).first()

    if not admin:
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

    symbols = session.query(Symbol).all()
    for i, symbol in enumerate(symbols):
        if i >= 12:
            break

        row = i // 4
        col = i % 4
        board_symbol = BoardSymbol(
            board_id=board.id,
            symbol_id=symbol.id,
            position_x=col,
            position_y=row,
            is_visible=True,
        )
        session.add(board_symbol)

    session.flush()


def _create_sample_users(session):
    """Create sample users for testing/demos with non-hardcoded passwords."""
    from src.aac_app.services.auth_service import get_password_hash

    sample_users = [
        ("student1", "Alex", "student"),
        ("teacher1", "Ms. Johnson", "teacher"),
        ("admin1", "Admin", "admin"),
    ]

    for username, display_name, user_type in sample_users:
        session.add(
            User(
                username=username,
                display_name=display_name,
                user_type=user_type,
                password_hash=get_password_hash(_seed_password_for(username)),
            )
        )

    session.flush()


def _create_sample_symbols(session):
    """Create sample communication symbols."""
    sample_symbols = [
        Symbol(
            label="cow",
            description="A farm animal that gives milk",
            category="farm_animals",
            keywords="cow, farm, milk, animal",
        ),
        Symbol(
            label="horse",
            description="A large animal you can ride",
            category="farm_animals",
            keywords="horse, farm, ride, animal",
        ),
        Symbol(
            label="chicken",
            description="A bird that lays eggs",
            category="farm_animals",
            keywords="chicken, farm, eggs, bird",
        ),
        Symbol(
            label="apple",
            description="A red fruit",
            category="food",
            keywords="apple, fruit, red, food",
        ),
        Symbol(
            label="water",
            description="Clear liquid for drinking",
            category="drinks",
            keywords="water, drink, liquid",
        ),
    ]

    for symbol in sample_symbols:
        session.add(symbol)
    session.flush()


def _create_sample_achievements(session):
    """Create sample achievements."""
    sample_achievements = [
        Achievement(
            name="First Steps",
            description="Complete your first learning session",
            category="beginner",
            criteria_type="sessions_completed",
            criteria_value=1,
        ),
        Achievement(
            name="Vocabulary Explorer",
            description="Learn 10 new words",
            category="vocabulary",
            criteria_type="vocabulary_size",
            criteria_value=10,
        ),
        Achievement(
            name="Quick Learner",
            description="Answer 5 questions correctly",
            category="performance",
            criteria_type="correct_answers",
            criteria_value=5,
        ),
    ]

    for achievement in sample_achievements:
        session.add(achievement)
    session.flush()
