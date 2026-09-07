from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.aac_app.models.achievement import ACHIEVEMENT_CRITERIA_TYPES

PreferenceLanguage = Annotated[str, Field(min_length=2, max_length=10)]

# Column-mirroring bounds shared by every schema field AND the raw-dict/login
# route checks that bypass schemas (auth.py's username bound, auth_users.py's
# admin-edit bounds). Single home so the next column change cannot touch three
# files and diverge the way the D2/D3 class did.
USERNAME_MAX_LENGTH = 50  # User.username String(50)
DISPLAY_NAME_MAX_LENGTH = 100  # User.display_name String(100)
EMAIL_MAX_LENGTH = 100  # User.email String(100)

# Password length bound shared by every password-accepting schema. Argon2/
# bcrypt hashing cost grows with the input, so an unbounded passphrase on the
# rate-limited-but-unauthenticated register/login endpoints would be CPU/memory
# amplification per request (a DoS bound, not a column bound: the stored hash
# is what the String(255) column holds). 200 is far above any legitimate
# passphrase and well below what should ever reach the hasher.
PASSWORD_MAX_LENGTH = 200

# Speaking-rate bounds for Kokoro TTS. Single backend home: the preference
# update schema, the synthesize endpoint schema (providers.py) and the legacy
# value clamp (auth_helpers.bounded_speed) all import these, so the three
# copies cannot drift apart.
TTS_SPEED_MIN = 0.5
TTS_SPEED_MAX = 2.0


class UserPreferencesResponse(BaseModel):
    tts_provider: str = "kokoro"
    tts_voice: str = "default"
    tts_local_voice: str = "default"
    tts_local_speed: float = 1.0
    tts_language: str | None = None
    ui_language: str | None = None
    notifications_enabled: bool = True
    voice_mode_enabled: bool = True
    dark_mode: bool = False
    dwell_time: int = 0
    ignore_repeats: int = 0
    high_contrast: bool = False
    hover_speak_enabled: bool = False
    hover_speak_delay_ms: int = 1000
    default_learning_mode: str = "practice"

    model_config = ConfigDict(from_attributes=True)


class UserPreferencesUpdate(BaseModel):
    tts_provider: Literal["browser", "kokoro"] | None = None
    # Browser voiceURIs ("Microsoft Sabina - Spanish (Mexico)") exceed any
    # short cap; mirror the widened UserSettings.tts_voice String(200) column.
    tts_voice: str | None = Field(None, max_length=200)
    tts_local_voice: str | None = Field(None, max_length=40)  # String(40): verified aligned
    # Same bounds as the Kokoro synthesis endpoint (providers.py).
    tts_local_speed: float | None = Field(None, ge=TTS_SPEED_MIN, le=TTS_SPEED_MAX)
    tts_language: PreferenceLanguage | None = None
    ui_language: PreferenceLanguage | None = None
    notifications_enabled: bool | None = None
    voice_mode_enabled: bool | None = None
    dark_mode: bool | None = None
    # Negative values are rejected with a localized 400 by
    # validate_preference_updates; only the upper bound is enforced here so
    # legacy clients keep receiving the translated error.
    dwell_time: int | None = Field(None, le=2000)
    ignore_repeats: int | None = Field(None, le=2000)
    high_contrast: bool | None = None
    hover_speak_enabled: bool | None = None
    default_learning_mode: str | None = Field(
        None,
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    # Hover-to-speak delay: sub-200ms values fire on accidental fly-bys,
    # anything above 5s is indistinguishable from a disabled feature.
    hover_speak_delay_ms: int | None = Field(None, le=5000)


def _strip_or_passthrough(value: object) -> object:
    """Strip a string value before pydantic's length constraints run.

    Single home for the pre-check strip that every user-name field needs
    (registration, profile update, change-password username): a padded value
    (" admin1 ") is measured by its stripped length, so it can neither sneak
    past the column-mirroring max_length nor create a look-alike row for the
    exact username/display-name match other paths perform. Non-strings pass
    through untouched (pydantic reports its own type error for them).
    """
    if isinstance(value, str):
        return value.strip()
    return value


# --- User Schemas ---
class UserBase(BaseModel):
    # Bounds mirror the User columns (username String(50), display_name
    # String(100), email String(100) — see models/user.py) so oversized
    # input fails clean 422 validation instead of 500ing on Postgres. Both
    # name fields are stripped BEFORE the length check: a padded value
    # (" admin1 ") can no longer create a look-alike row for the exact
    # username match that login and the availability pre-check perform, and
    # a whitespace-only value is rejected as empty. No charset regex is
    # imposed (none exists elsewhere in the repo): normalization is strip +
    # non-empty only.
    username: str = Field(..., min_length=1, max_length=USERNAME_MAX_LENGTH)
    email: EmailStr | None = Field(None, max_length=EMAIL_MAX_LENGTH)
    display_name: str = Field(..., min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    user_type: str = "student"

    @field_validator("username", "display_name", mode="before")
    @classmethod
    def _strip_user_name_fields(cls, value: object) -> object:
        return _strip_or_passthrough(value)


class UserCreate(UserBase):
    """Public self-registration payload.

    ``confirm_password`` is optional (the registration form has no
    confirmation field) and, when supplied, is compared against ``password``
    by the route (a mismatch is a hard 400, never a silent ignore).
    ``created_by_teacher_id`` stays on the shared contract ON PURPOSE: a
    shared registration client may carry the teacher's id, and public
    registration deliberately ignores it (never auto-assigns, never grants a
    privilege) — a contract pinned by tests/test_auth_auto_assignment.py.
    """

    password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)
    confirm_password: str | None = Field(None, max_length=PASSWORD_MAX_LENGTH)
    created_by_teacher_id: int | None = None  # Ignored by public register


class StaffStudentCreate(UserCreate):
    """Staff (teacher/admin) student-creation payload.

    Adds an optional per-student safety configuration applied atomically at
    creation. ``created_by_teacher_id`` is read by the staff route (teachers
    are always auto-assigned to themselves; an admin may name an active
    teacher). Public registration intentionally ignores it.
    """

    # String annotation: StudentSafetyCreate is defined later in this module
    # (it reuses SafetyConstraintsSchema); pydantic resolves it at build time.
    safety: "StudentSafetyCreate | None" = None


class UserProfileUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=DISPLAY_NAME_MAX_LENGTH)
    email: EmailStr | None = Field(None, max_length=EMAIL_MAX_LENGTH)

    @field_validator("display_name", mode="before")
    @classmethod
    def _strip_display_name(cls, value: object) -> object:
        # Strip BEFORE the max_length check, exactly like UserBase does for
        # registration: a padded valid name ("  " + 99 chars + "  ") is the
        # same human name that registration accepts and stores stripped, so
        # the profile edit must not 422 it. A whitespace-only value still
        # fails in the route's blank-name check (400), not here.
        return _strip_or_passthrough(value)


class ChangePasswordRequest(BaseModel):
    # Username bound mirrors the User column (String(50)) with a strip
    # before-validator, like UserBase: an overlong or padded value cannot
    # slip past into the lockout/audit storage of the password flow.
    username: str = Field(..., min_length=1, max_length=USERNAME_MAX_LENGTH)
    current_password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)
    confirm_password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)

    @field_validator("username", mode="before")
    @classmethod
    def _strip_username(cls, value: object) -> object:
        return _strip_or_passthrough(value)


class ResetPasswordRequest(BaseModel):
    student_id: int | None = None
    user_id: int | None = None
    new_password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)


class UserResponse(BaseModel):
    """Output contract for a user row.

    Deliberately independent from ``UserBase``: the input schema enforces
    ``min_length`` + strip so every NEW write stores a non-empty name, while
    rows written before those bounds existed (or written by direct SQL) may
    legally keep ``display_name=""``. Applying the input bounds on the way
    out would turn reading those legacy rows into a 500
    ``ResponseValidationError``; the output keeps only the column-aligned
    ``max_length`` caps.
    """

    id: int
    username: str = Field(..., max_length=USERNAME_MAX_LENGTH)
    email: EmailStr | None = None
    display_name: str = Field(..., max_length=DISPLAY_NAME_MAX_LENGTH)
    user_type: str = "student"
    is_active: bool
    created_at: datetime
    settings: UserPreferencesResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class SetupStatusResponse(BaseModel):
    setup_required: bool
    has_admin: bool
    app_name: str
    app_version: str


# Documented fallbacks for the first-run setup payload (applied AFTER strip,
# exactly like the route's ``payload.username.strip() or "admin1"`` behavior).
# Kept here so the before-validator below and the route cannot drift apart.
SETUP_DEFAULT_USERNAME = "admin1"
SETUP_DEFAULT_DISPLAY_NAME = "Administrator"


class InitialAdminSetupRequest(BaseModel):
    """First-run administrator payload.

    username/display_name mirror the User columns (String(50)/String(100)) so
    an oversized value fails clean validation instead of 500ing on Postgres
    when the User row is flushed. Unlike UserBase this schema does NOT treat a
    whitespace-only value as an error: the documented fallback semantics are
    strip -> default-if-empty -> column bound check, so ``"   "`` still yields
    ``admin1``/``Administrator`` (a naive ``min_length=1`` would 422 it).
    """

    username: str = Field(SETUP_DEFAULT_USERNAME, max_length=USERNAME_MAX_LENGTH)
    display_name: str = Field(SETUP_DEFAULT_DISPLAY_NAME, max_length=DISPLAY_NAME_MAX_LENGTH)
    email: EmailStr | None = Field(None, max_length=EMAIL_MAX_LENGTH)
    password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)
    confirm_password: str = Field(..., max_length=PASSWORD_MAX_LENGTH)

    @field_validator("username", "display_name", mode="before")
    @classmethod
    def _setup_name_strip_or_default(cls, value: object, info: Any) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped:
            return stripped
        return (
            SETUP_DEFAULT_USERNAME
            if info.field_name == "username"
            else SETUP_DEFAULT_DISPLAY_NAME
        )


class SetupResponse(BaseModel):
    message: str
    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    refresh_token: str


class BoardSummaryResponse(BaseModel):
    """Lightweight board data used in student-management summaries."""

    id: int
    user_id: int
    name: str
    description: str | None = None
    category: str = "general"
    is_public: bool = False
    is_template: bool = False
    created_at: datetime
    updated_at: datetime
    grid_rows: int | None = 4
    grid_cols: int | None = 5
    ai_enabled: bool = False
    ai_provider: str | None = None
    ai_model: str | None = None
    locale: str = Field("en", min_length=2, max_length=10)
    is_language_learning: bool = False
    symbols: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class StudentBoardSummaryResponse(BaseModel):
    """A student and assigned boards returned in one API request."""

    id: int
    username: str
    email: EmailStr | None = None
    display_name: str
    user_type: str = "student"
    is_active: bool
    created_at: datetime
    assigned_boards: list[BoardSummaryResponse] = Field(default_factory=list)


# --- Learning Mode Schemas ---
class LearningModeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    key: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(None, max_length=10_000)
    prompt_instruction: str = Field(..., min_length=1, max_length=10_000)
    # Auto-ask adaptive questions in sessions using this mode (default on).
    auto_ask_enabled: bool = True

class LearningModeCreate(LearningModeBase):
    pass

class LearningModeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10_000)
    prompt_instruction: str | None = Field(None, min_length=1, max_length=10_000)
    auto_ask_enabled: bool | None = None

class LearningModeResponse(LearningModeBase):
    id: int
    is_custom: bool
    created_by: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SavedTopicCreate(BaseModel):
    """Payload for saving a topic from the teacher/admin sidebar."""

    board: str = Field("", max_length=100)
    board_id: int | None = None
    topic: str = Field(..., min_length=1, max_length=200)

class SavedTopicResponse(BaseModel):
    """A saved topic as exposed to teachers/admins (owners) and students."""

    id: int
    user_id: int
    board: str
    board_id: int | None = None
    topic: str
    created_by: str
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class LearningModePreviewRequest(BaseModel):
    """Preview the exact LLM system prompt a learning mode would produce."""

    mode_key: str | None = None
    # Raw instruction for modes that have not been saved yet; takes
    # precedence over a mode_key lookup when provided.
    prompt_instruction: str | None = None
    # Optional student to preview against (uses their guardian profile).
    student_id: int | None = None
    # When provided, the response also includes the exact user message the
    # LLM would receive for this student's question ("Preview with sample
    # question").
    sample_question: str | None = None
    # Optional session topic used when rendering the sample-question message.
    topic: str | None = None

class LearningModePreviewResponse(BaseModel):
    """Rendered system prompt with preview metadata."""

    prompt: str
    template_name: str = "default"
    has_guardian_profile: bool = False
    mode_instruction: str | None = None
    # The exact user message for the sample question (None when no sample
    # question was requested).
    user_message: str | None = None
    # The full chat request as sent to the LLM: [system, user].
    messages: list[dict] | None = None
    # Model parameters used for conversational calls.
    temperature: float | None = None
    max_tokens: int | None = None


# --- Board Schemas ---
class SymbolBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10_000)
    category: str = Field("general", min_length=1, max_length=50)
    image_path: str | None = Field(None, max_length=255)  # Symbol.image_path String(255)
    audio_path: str | None = Field(None, max_length=255)  # Symbol.audio_path String(255)
    keywords: str | None = Field(None, max_length=10_000)
    language: str = Field("en", min_length=2, max_length=10)


class SymbolCreate(SymbolBase):
    pass


class SymbolResponse(SymbolBase):
    id: int
    is_builtin: bool
    created_at: datetime | None = None
    is_in_use: bool = False

    model_config = ConfigDict(from_attributes=True)


class SymbolUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10_000)
    category: str | None = Field(None, min_length=1, max_length=50)
    image_path: str | None = Field(None, max_length=255)  # Symbol.image_path String(255)
    audio_path: str | None = Field(None, max_length=255)  # Symbol.audio_path String(255)
    keywords: str | None = Field(None, max_length=10_000)
    language: str | None = Field(None, min_length=2, max_length=10)


class SymbolReorderUpdate(BaseModel):
    """Schema for symbol reorder update"""

    id: int = Field(..., description="Symbol ID")
    order_index: int = Field(..., ge=0, description="New order index (must be >= 0)")


class BoardSymbolBase(BaseModel):
    symbol_id: int
    position_x: int = Field(0, ge=0)
    position_y: int = Field(0, ge=0)
    size: int = Field(1, ge=1, le=100)
    is_visible: bool = True
    custom_text: str | None = Field(None, max_length=100)
    color: str | None = Field(None, max_length=20)
    linked_board_id: int | None = Field(None, ge=1)


class BoardSymbolCreate(BoardSymbolBase):
    pass


class BoardSymbolUpdate(BaseModel):
    symbol_id: int | None = None
    position_x: int | None = Field(None, ge=0)
    position_y: int | None = Field(None, ge=0)
    size: int | None = Field(None, ge=1, le=100)
    is_visible: bool | None = None
    custom_text: str | None = Field(None, max_length=100)
    color: str | None = Field(None, max_length=20)
    linked_board_id: int | None = Field(None, ge=1)


class BoardSymbolBatchUpdate(BoardSymbolUpdate):
    """Validated placement update used by the board editor batch endpoint."""

    # Older board-editor clients may include placeholder entries without an
    # association ID; the endpoint intentionally ignores those entries.
    id: int | None = Field(None, ge=1, description="Board-symbol placement ID")


class BoardSymbolResponse(BoardSymbolBase):
    id: int
    symbol: SymbolResponse

    model_config = ConfigDict(from_attributes=True)


class BoardBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10_000)
    category: str = Field("general", min_length=1, max_length=50)
    is_public: bool = False
    is_template: bool = False
    grid_rows: int | None = Field(4, ge=1, le=100)
    grid_cols: int | None = Field(5, ge=1, le=100)
    ai_enabled: bool = False
    ai_provider: str | None = None
    ai_model: str | None = Field(None, max_length=100)  # CommunicationBoard.ai_model String(100)
    locale: str = Field("en", min_length=2, max_length=10)
    is_language_learning: bool = False


class BoardCreate(BoardBase):
    symbols: list[BoardSymbolCreate] | None = None


class BoardUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10_000)
    category: str | None = Field(None, max_length=50)
    is_public: bool | None = None
    is_template: bool | None = None
    grid_rows: int | None = Field(None, ge=1, le=100)
    grid_cols: int | None = Field(None, ge=1, le=100)
    ai_enabled: bool | None = None
    ai_provider: str | None = None
    ai_model: str | None = Field(None, max_length=100)  # CommunicationBoard.ai_model String(100)
    locale: str | None = Field(None, min_length=2, max_length=10)
    is_language_learning: bool | None = None


class BoardResponse(BoardBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    symbols: list[BoardSymbolResponse] = Field(default_factory=list)
    playable_symbols_count: int | None = 0

    model_config = ConfigDict(from_attributes=True)


class AISuggestion(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    symbol_key: str | None = Field(None, max_length=100)
    color: str | None = Field(None, max_length=20)
    linked_board_id: int | None = Field(None, ge=1)
    description: str | None = None


class AISuggestionsRequest(BaseModel):
    refine_prompt: str | None = None
    regenerate: bool = False
    item_count: int | None = Field(None, ge=1, le=100)


class AISuggestionApplyRequest(BaseModel):
    item: AISuggestion
    position_x: int | None = Field(None, ge=0)
    position_y: int | None = Field(None, ge=0)


# --- Notification Schemas ---
class NotificationCreate(BaseModel):
    user_id: int
    # Bounds mirror the Notification columns (title String(200),
    # notification_type/priority String(20)) so oversize input fails
    # validation instead of blowing up on Postgres.
    title: str = Field(..., min_length=1, max_length=200)
    message: str
    notification_type: str = Field("info", min_length=1, max_length=20)
    priority: str = Field("normal", min_length=1, max_length=20)


class BoardAssignRequest(BaseModel):
    student_id: int
    assigned_by: int | None = None


class StudentAssignRequest(BaseModel):
    student_id: int
    teacher_id: int
    assigned_by: int | None = None


# --- Learning Schemas ---
# Real difficulty bands used by the question engine (learning/common.py:
# difficulty_for_score). Anything else would leak into the LLM prompt and be
# persisted on the session row, so the start payload only accepts these.
DifficultyBand = Literal["basic", "intermediate", "advanced"]


class LearningSessionStart(BaseModel):
    topic: str = Field(..., min_length=1, max_length=100)
    purpose: str | None = Field(None, max_length=10_000)
    difficulty: DifficultyBand = "basic"
    board_id: int | None = Field(None, ge=1)
    mode_key: str | None = Field(None, min_length=1, max_length=50)


class LearningSessionResponse(BaseModel):
    success: bool
    session_id: int
    plan_id: int | None = None
    task_id: int | None = None
    board_id: int | None = None
    welcome_message: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    provider_used: str | None = None
    summary: str | None = None
    comprehension_score: float | None = None
    questions_answered: int | None = None
    correct_answers: int | None = None
    statistics: dict[str, int | float] | None = None
    error: str | None = None


class QuestionResponse(BaseModel):
    success: bool
    question_id: int | None = None
    question_text: str | None = None
    choices: list[str] | None = None
    difficulty: str | None = None
    correct_answer_index: int | None = None
    provider_used: str | None = None
    error: str | None = None


class AnswerSubmit(BaseModel):
    # Bound text before it is copied into an LLM prompt and JSON history.
    answer: str = Field(..., min_length=1, max_length=10_000)
    is_voice: bool = False


class SymbolItem(BaseModel):
    id: int | None = Field(None, ge=1)
    label: str = Field(..., min_length=1, max_length=100)
    category: str | None = Field(None, max_length=50)
    image_path: str | None = Field(None, max_length=500)
    position: int | None = Field(None, ge=0)  # Order in utterance (0-indexed)
    weight: float | None = Field(1.0, ge=0.0, le=1.0)  # Confidence/emphasis


class SymbolAnswerSubmit(BaseModel):
    # Empty symbol lists are allowed through validation so the endpoint can
    # answer with a translated 400 (errors.noSymbolsProvided) instead of an
    # opaque Pydantic 422 validation array.
    symbols: list[SymbolItem] = Field(..., max_length=100)
    text: str | None = Field(None, max_length=10_000)  # Deprecated: use enriched_gloss
    raw_gloss: str | None = Field(None, max_length=10_000)  # Simple concatenation of labels
    enriched_gloss: str | None = Field(None, max_length=10_000)  # Template-enhanced gloss
    context_hint: str | None = Field(None, max_length=10_000)  # Optional user-provided context


class AnswerResponse(BaseModel):
    success: bool
    is_correct: bool | None = None
    transcription: str | None = None
    feedback_message: str | None = None
    # True once the tutor has revealed the full correct answer after enough
    # failed attempts; the UI may then auto-advance to the next question.
    answer_revealed: bool | None = None
    confidence: float | None = None
    comprehension_score: float | None = None
    next_action: str | None = None
    questions_answered: int | None = None
    correct_answers: int | None = None
    provider_used: str | None = None
    error: str | None = None


# --- Achievement Schemas ---
class AchievementBase(BaseModel):
    name: str
    description: str
    category: str
    points: int
    icon: str = "🏆"  # Default icon if none provided


class AchievementResponse(AchievementBase):
    earned_at: str | None = None
    progress: float = 1.0

    model_config = ConfigDict(from_attributes=True)


# The canonical tuple lives in the models layer
# (aac_app/models/achievement.py) and is imported here for the wire Literal;
# the schema must not re-declare the values so a service importing this module
# can never accidentally depend on api.schemas.
AchievementCriteriaType = Literal[*ACHIEVEMENT_CRITERIA_TYPES]


class AchievementCreate(BaseModel):
    """Create a custom achievement"""

    name: str = Field(..., min_length=1, max_length=100)
    # Description is optional: the editor allows leaving it blank, so an empty
    # string must not be rejected by validation (it is stored as-is).
    description: str = Field("", max_length=10_000)
    category: str = Field("custom", min_length=1, max_length=50)
    points: int = Field(10, ge=0)
    icon: str = Field("🏆", min_length=1, max_length=50)
    target_user_id: int | None = Field(None, ge=1)  # If set, only this user sees it
    criteria_type: AchievementCriteriaType | None = None
    criteria_value: float | None = Field(None, ge=0)


class AchievementUpdate(BaseModel):
    """Update an achievement"""

    name: str | None = Field(None, min_length=1, max_length=100)
    # Description is optional; an empty string is a valid value (editor allows
    # clearing it). Only the length limit applies.
    description: str | None = Field(None, max_length=10_000)
    category: str | None = Field(None, min_length=1, max_length=50)
    points: int | None = Field(None, ge=0)
    icon: str | None = Field(None, min_length=1, max_length=50)
    is_active: bool | None = None
    target_user_id: int | None = Field(None, ge=1)
    criteria_type: AchievementCriteriaType | None = None
    criteria_value: float | None = Field(None, ge=0)


class AchievementFullResponse(BaseModel):
    """Full achievement details including management info"""
    id: int
    name: str
    description: str
    category: str
    points: int
    icon: str
    is_manual: bool = False
    created_by: int | None = None
    target_user_id: int | None = None
    is_active: bool = True
    created_at: datetime | None = None
    criteria_type: str | None = None
    criteria_value: float | None = None

    model_config = ConfigDict(from_attributes=True)


class AchievementAward(BaseModel):
    """Award an achievement to a user"""
    user_id: int


class LeaderboardEntry(BaseModel):
    username: str
    display_name: str
    points: int
    achievement_count: int


# --- Analytics Schemas ---
class SymbolUsageItem(BaseModel):
    # Bounds mirror the SymbolUsageLog columns (symbol_label String(50),
    # symbol_category String(50), see models/analytics.py) so oversized
    # telemetry fails validation instead of 500ing on Postgres inside the
    # best-effort savepoint (which catches only IntegrityError).
    id: int = Field(..., ge=1)
    label: str = Field(..., min_length=1, max_length=50)
    category: str | None = Field(None, max_length=50)


class SymbolUsageRequest(BaseModel):
    symbols: list[SymbolUsageItem]
    session_id: int | None = None
    # Column widths (semantic_intent String(20), context_topic String(100))
    # bound the optional telemetry strings the same way the item fields are.
    semantic_intent: str | None = Field(None, max_length=20)
    context_topic: str | None = Field(None, max_length=100)


class NextSymbolRequest(BaseModel):
    # ``current_symbols`` is comma-split into per-label predictions: 2000
    # chars comfortably covers any real utterance while capping the list
    # size. ``topic`` mirrors the SavedTopic/search param bound (200): it is
    # tokenized into one SQL LIKE expression per token, so an unbounded topic
    # would build a pathological query and mint giant cache keys.
    current_symbols: str = Field("", max_length=2000)
    limit: int = Field(5, ge=1, le=50)
    intent: str = "general"
    offset: int = Field(0, ge=0, le=100_000)
    board_id: int | None = None
    topic: str | None = Field(None, max_length=200)


# --- Guardian Profile Schemas (Learning Companion Personality) ---


class MedicalContextSchema(BaseModel):
    """Medical/accessibility context for a student (confidential)"""

    diagnoses: list[str] | None = None
    sensitivities: list[str] | None = None
    accessibility_needs: list[str] | None = None
    notes: str | None = None


class CommunicationStyleSchema(BaseModel):
    """Communication style preferences for the companion"""

    tone: str | None = None  # encouraging, calm, playful, professional
    complexity: str | None = None  # simple, moderate, advanced
    sentence_length: str | None = None  # short, medium, long
    vocabulary_level: str | None = None
    use_emojis: bool | None = None
    avoid_idioms: bool | None = None
    avoid_sarcasm: bool | None = None
    avoid_metaphors: bool | None = None
    explicit_transitions: bool | None = None


class SafetyConstraintsSchema(BaseModel):
    """Safety configuration for content filtering (Layer 1 + 2)."""

    content_filter_level: str | None = None  # strict, standard, relaxed
    forbidden_topics: list[str] | None = None
    trigger_words: list[str] | None = None
    # >=1 only: 0/negative feedback caps corrupt replies (a 0-length slice),
    # and the UI clears the cap with null/undefined.
    max_response_length: int | None = Field(None, ge=1)
    # Per-student feature gates. ``None`` = follow the admin global setting.
    block_ai_chat: bool | None = None
    block_board_ai: bool | None = None
    block_custom_topics: bool | None = None
    block_autogen_pictograms: bool | None = None
    block_social_messaging: bool | None = None
    # Strict-level LLM moderation sentinel on chat output.
    sentinel_moderation: bool | None = None


class StudentSafetyCreate(SafetyConstraintsSchema):
    """Per-student safety configuration supplied at account creation."""

    age: int | None = Field(None, ge=1, le=100, description="Student age (1-100)")


class CompanionPersonaSchema(BaseModel):
    """Companion persona customization"""

    name: str | None = None
    role: str | None = None
    personality: list[str] | None = None
    greeting_style: str | None = None  # consistent, varied
    sign_off_style: str | None = None


class GuardianProfileFields(BaseModel):
    """Shared editable fields for guardian profile create and update."""

    age: int | None = Field(None, ge=1, le=100, description="Student age (1-100)")
    gender: str | None = Field(None, max_length=30)  # GuardianProfile.gender String(30)
    medical_context: MedicalContextSchema | None = None
    communication_style: CommunicationStyleSchema | None = None
    safety_constraints: SafetyConstraintsSchema | None = None
    companion_persona: CompanionPersonaSchema | None = None
    custom_instructions: str | None = None
    private_notes: str | None = None


class GuardianProfileCreate(GuardianProfileFields):
    """Create a new guardian profile for a student"""

    template_name: str = "default"


class GuardianProfileUpdate(GuardianProfileFields):
    """Update an existing guardian profile"""

    template_name: str | None = None
    change_reason: str | None = None  # For audit trail


class GuardianProfileResponse(BaseModel):
    """Guardian profile response with full details"""

    id: int
    user_id: int
    template_name: str
    age: int | None = None
    gender: str | None = None
    medical_context: MedicalContextSchema | None = None
    communication_style: CommunicationStyleSchema | None = None
    safety_constraints: SafetyConstraintsSchema | None = None
    companion_persona: CompanionPersonaSchema | None = None
    custom_instructions: str | None = None
    private_notes: str | None = None
    is_active: bool = True
    created_by: int
    updated_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ContentSafetyPolicySchema(BaseModel):
    """Admin-configurable global content policy (server-wide default)."""

    level: str = "standard"
    forbidden_topics: list[str] = []
    trigger_words: list[str] = []
    feature_locks: dict[str, bool] = {}
    sentinel_moderation: bool = False
    max_response_length: int | None = Field(None, ge=1)
    # Fields teachers may not override per student.
    locked_fields: list[str] = []


class ContentSafetyEventSchema(BaseModel):
    """One logged content-safety verdict."""

    id: int
    user_id: int | None = None
    surface: str
    direction: str
    verdict: str
    matched: list[str] = []
    detail: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfileHistoryEntry(BaseModel):
    """A single history entry for profile changes"""

    id: int
    field_name: str
    old_value: Any | None = None
    new_value: Any | None = None
    changed_by: dict
    changed_at: str | None = None
    change_reason: str | None = None


class TemplateInfo(BaseModel):
    """Template metadata"""

    name: str
    display_name: str
    description: str
    version: str


class StudentWithProfileInfo(BaseModel):
    """Student info with profile status"""

    id: int
    username: str
    display_name: str
    has_profile: bool
    template_name: str | None = None
    profile_created_at: str | None = None


class SystemPromptPreview(BaseModel):
    """Preview of a rendered system prompt"""

    template_name: str
    prompt: str
