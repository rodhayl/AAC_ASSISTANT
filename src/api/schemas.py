from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPreferencesResponse(BaseModel):
    tts_voice: str = "default"
    tts_language: str | None = None
    ui_language: str | None = None
    notifications_enabled: bool = True
    voice_mode_enabled: bool = True
    dark_mode: bool = False
    dwell_time: int = 0
    ignore_repeats: int = 0
    high_contrast: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserPreferencesUpdate(BaseModel):
    tts_voice: str | None = None
    tts_language: str | None = None
    ui_language: str | None = None
    notifications_enabled: bool | None = None
    voice_mode_enabled: bool | None = None
    dark_mode: bool | None = None
    dwell_time: int | None = None
    ignore_repeats: int | None = None
    high_contrast: bool | None = None


# --- User Schemas ---
class UserBase(BaseModel):
    username: str
    email: EmailStr | None = None
    display_name: str
    user_type: str = "student"


class UserCreate(UserBase):
    password: str
    confirm_password: str | None = None  # Required for admin-created users
    created_by_teacher_id: int | None = None  # Auto-assign student to this teacher


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    settings: UserPreferencesUpdate | None = None


class UserProfileUpdate(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None


class LoginRequest(BaseModel):
    """Deprecated JSON login contract retained for external clients."""

    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    username: str
    current_password: str
    new_password: str
    confirm_password: str


class ResetPasswordRequest(BaseModel):
    student_id: int | None = None
    user_id: int | None = None
    new_password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    settings: UserPreferencesResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class SetupStatusResponse(BaseModel):
    setup_required: bool
    has_admin: bool
    app_name: str
    app_version: str


class InitialAdminSetupRequest(BaseModel):
    username: str = "admin1"
    display_name: str = "Administrator"
    email: EmailStr | None = None
    password: str
    confirm_password: str


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
    locale: str = "en"
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
    label: str
    description: str | None = None
    category: str = "general"
    image_path: str | None = None
    audio_path: str | None = None
    keywords: str | None = None
    language: str = "en"


class SymbolCreate(SymbolBase):
    pass


class SymbolResponse(SymbolBase):
    id: int
    is_builtin: bool
    created_at: datetime | None = None
    is_in_use: bool = False

    model_config = ConfigDict(from_attributes=True)


class SymbolUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    category: str | None = None
    image_path: str | None = None
    audio_path: str | None = None
    keywords: str | None = None
    language: str | None = None


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
    custom_text: str | None = None
    color: str | None = None
    linked_board_id: int | None = Field(None, ge=1)


class BoardSymbolCreate(BoardSymbolBase):
    pass


class BoardSymbolUpdate(BaseModel):
    symbol_id: int | None = None
    position_x: int | None = Field(None, ge=0)
    position_y: int | None = Field(None, ge=0)
    size: int | None = Field(None, ge=1, le=100)
    is_visible: bool | None = None
    custom_text: str | None = None
    color: str | None = None
    linked_board_id: int | None = Field(None, ge=1)


class BoardSymbolResponse(BoardSymbolBase):
    id: int
    symbol: SymbolResponse

    model_config = ConfigDict(from_attributes=True)


class BoardBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10_000)
    category: str = Field("general", max_length=50)
    is_public: bool = False
    is_template: bool = False
    grid_rows: int | None = Field(4, ge=1, le=100)
    grid_cols: int | None = Field(5, ge=1, le=100)
    ai_enabled: bool = False
    ai_provider: str | None = None
    ai_model: str | None = None
    locale: str = "en"
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
    ai_model: str | None = None
    locale: str | None = None
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
    title: str
    message: str
    notification_type: str = "info"
    priority: str = "normal"


class BoardAssignRequest(BaseModel):
    student_id: int
    assigned_by: int | None = None


class StudentAssignRequest(BaseModel):
    student_id: int
    teacher_id: int
    assigned_by: int | None = None


# --- Learning Schemas ---
class LearningSessionStart(BaseModel):
    topic: str
    purpose: str | None = None
    difficulty: str = "basic"
    board_id: int | None = None
    mode_key: str | None = None


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
    answer: str
    is_voice: bool = False


class SymbolItem(BaseModel):
    id: int | None = None
    label: str
    category: str | None = None
    image_path: str | None = None
    position: int | None = None  # Order in utterance (0-indexed)
    weight: float | None = 1.0  # Confidence/emphasis (for future use)


class SymbolAnswerSubmit(BaseModel):
    symbols: list[SymbolItem]
    text: str | None = None  # Deprecated: use enriched_gloss
    raw_gloss: str | None = None  # Simple concatenation of labels
    enriched_gloss: str | None = None  # Template-enhanced gloss
    context_hint: str | None = None  # Optional user-provided context


class AnswerResponse(BaseModel):
    success: bool
    is_correct: bool | None = None
    transcription: str | None = None
    feedback_message: str | None = None
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


class AchievementCreate(BaseModel):
    """Create a custom achievement"""
    name: str
    description: str
    category: str = "custom"
    points: int = 10
    icon: str = "🏆"
    target_user_id: int | None = None  # If set, only this user sees it
    criteria_type: str | None = None
    criteria_value: float | None = None


class AchievementUpdate(BaseModel):
    """Update an achievement"""
    name: str | None = None
    description: str | None = None
    category: str | None = None
    points: int | None = None
    icon: str | None = None
    is_active: bool | None = None
    criteria_type: str | None = None
    criteria_value: float | None = None


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
    id: int
    label: str
    category: str | None = None


class SymbolUsageRequest(BaseModel):
    symbols: list[SymbolUsageItem]
    session_id: int | None = None
    semantic_intent: str | None = None
    context_topic: str | None = None


class NextSymbolRequest(BaseModel):
    current_symbols: str = ""
    chat_history: list[dict[str, str]] = Field(default_factory=list)
    limit: int = Field(5, ge=1, le=50)
    intent: str = "general"
    offset: int = Field(0, ge=0, le=100_000)
    board_id: int | None = None


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
    """Safety configuration for content filtering"""

    content_filter_level: str | None = None  # strict, standard, relaxed
    forbidden_topics: list[str] | None = None
    trigger_words: list[str] | None = None
    max_response_length: int | None = None


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
    gender: str | None = None
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
    medical_context: dict | None = None
    communication_style: dict | None = None
    safety_constraints: dict | None = None
    companion_persona: dict | None = None
    custom_instructions: str | None = None
    private_notes: str | None = None
    is_active: bool = True
    created_by: int
    updated_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

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
