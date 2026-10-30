from datetime import datetime
from typing import Any, List, Optional, Dict

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPreferencesResponse(BaseModel):
    tts_voice: str = "default"
    tts_language: Optional[str] = None
    ui_language: Optional[str] = None
    notifications_enabled: bool = True
    voice_mode_enabled: bool = True
    dark_mode: bool = False
    dwell_time: int = 0
    ignore_repeats: int = 0
    high_contrast: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserPreferencesUpdate(BaseModel):
    tts_voice: Optional[str] = None
    tts_language: Optional[str] = None
    ui_language: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    voice_mode_enabled: Optional[bool] = None
    dark_mode: Optional[bool] = None
    dwell_time: Optional[int] = None
    ignore_repeats: Optional[int] = None
    high_contrast: Optional[bool] = None


# --- User Schemas ---
class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    display_name: str
    user_type: str = "student"


class UserCreate(UserBase):
    password: str
    confirm_password: Optional[str] = None  # Required for admin-created users
    created_by_teacher_id: Optional[int] = None  # Auto-assign student to this teacher


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None
    settings: Optional[UserPreferencesUpdate] = None


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    username: str
    current_password: str
    new_password: str
    confirm_password: str


class ResetPasswordRequest(BaseModel):
    student_id: Optional[int] = None
    user_id: Optional[int] = None
    new_password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    settings: Optional[UserPreferencesResponse] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


# --- Learning Mode Schemas ---
class LearningModeBase(BaseModel):
    name: str
    key: str
    description: Optional[str] = None
    prompt_instruction: str

class LearningModeCreate(LearningModeBase):
    pass

class LearningModeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt_instruction: Optional[str] = None

class LearningModeResponse(LearningModeBase):
    id: int
    is_custom: bool
    created_by: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Board Schemas ---
class SymbolBase(BaseModel):
    label: str
    description: Optional[str] = None
    category: str = "general"
    image_path: Optional[str] = None
    audio_path: Optional[str] = None
    keywords: Optional[str] = None
    language: str = "en"


class SymbolCreate(SymbolBase):
    pass


class SymbolResponse(SymbolBase):
    id: int
    is_builtin: bool
    created_at: Optional[datetime] = None
    is_in_use: bool = False

    model_config = ConfigDict(from_attributes=True)


class SymbolUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_path: Optional[str] = None
    audio_path: Optional[str] = None
    keywords: Optional[str] = None
    language: Optional[str] = None


class SymbolReorderUpdate(BaseModel):
    """Schema for symbol reorder update"""

    id: int = Field(..., description="Symbol ID")
    order_index: int = Field(..., ge=0, description="New order index (must be >= 0)")


class BoardSymbolBase(BaseModel):
    symbol_id: int
    position_x: int = 0
    position_y: int = 0
    size: int = 1
    is_visible: bool = True
    custom_text: Optional[str] = None
    color: Optional[str] = None
    linked_board_id: Optional[int] = None


class BoardSymbolCreate(BoardSymbolBase):
    pass


class BoardSymbolUpdate(BaseModel):
    symbol_id: Optional[int] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    size: Optional[int] = None
    is_visible: Optional[bool] = None
    custom_text: Optional[str] = None
    color: Optional[str] = None
    linked_board_id: Optional[int] = None


class BoardSymbolResponse(BoardSymbolBase):
    id: int
    symbol: SymbolResponse

    model_config = ConfigDict(from_attributes=True)


class BoardBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str = "general"
    is_public: bool = False
    is_template: bool = False
    grid_rows: Optional[int] = 4
    grid_cols: Optional[int] = 5
    ai_enabled: bool = False
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    locale: str = "en"
    is_language_learning: bool = False


class BoardCreate(BoardBase):
    symbols: Optional[List[BoardSymbolCreate]] = None


class BoardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_public: Optional[bool] = None
    is_template: Optional[bool] = None
    grid_rows: Optional[int] = None
    grid_cols: Optional[int] = None
    ai_enabled: Optional[bool] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    locale: Optional[str] = None
    is_language_learning: Optional[bool] = None


class BoardResponse(BoardBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    symbols: List[BoardSymbolResponse] = []
    playable_symbols_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class AISuggestion(BaseModel):
    label: str
    symbol_key: Optional[str] = None
    color: Optional[str] = None
    linked_board_id: Optional[int] = None
    description: Optional[str] = None


class AISuggestionsRequest(BaseModel):
    refine_prompt: Optional[str] = None
    regenerate: bool = False
    item_count: Optional[int] = None
    ai_source: Optional[str] = None  # 'primary' or 'fallback'


class AISuggestionApplyRequest(BaseModel):
    item: AISuggestion
    position_x: Optional[int] = None
    position_y: Optional[int] = None


# --- Notification Schemas ---
class NotificationCreate(BaseModel):
    user_id: int
    title: str
    message: str
    notification_type: str = "info"
    priority: str = "normal"


class BoardAssignRequest(BaseModel):
    student_id: int
    assigned_by: Optional[int] = None


class StudentAssignRequest(BaseModel):
    student_id: int
    teacher_id: int
    assigned_by: Optional[int] = None


# --- Learning Schemas ---
class LearningSessionStart(BaseModel):
    topic: str
    purpose: Optional[str] = None
    difficulty: str = "basic"
    board_id: Optional[int] = None


class LearningSessionResponse(BaseModel):
    success: bool
    session_id: int
    plan_id: Optional[int] = None
    task_id: Optional[int] = None
    board_id: Optional[int] = None
    welcome_message: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    provider_used: Optional[str] = None
    error: Optional[str] = None


class QuestionResponse(BaseModel):
    success: bool
    question_id: Optional[int] = None
    question_text: Optional[str] = None
    choices: Optional[List[str]] = None
    difficulty: Optional[str] = None
    correct_answer_index: Optional[int] = None
    provider_used: Optional[str] = None
    error: Optional[str] = None


class AnswerSubmit(BaseModel):
    answer: str
    is_voice: bool = False


class SymbolItem(BaseModel):
    id: Optional[int] = None
    label: str
    category: Optional[str] = None
    image_path: Optional[str] = None
    position: Optional[int] = None  # Order in utterance (0-indexed)
    weight: Optional[float] = 1.0  # Confidence/emphasis (for future use)


class SymbolAnswerSubmit(BaseModel):
    symbols: List[SymbolItem]
    text: Optional[str] = None  # Deprecated: use enriched_gloss
    raw_gloss: Optional[str] = None  # Simple concatenation of labels
    enriched_gloss: Optional[str] = None  # Template-enhanced gloss
    context_hint: Optional[str] = None  # Optional user-provided context


class AnswerResponse(BaseModel):
    success: bool
    is_correct: Optional[bool] = None
    transcription: Optional[str] = None
    feedback_message: Optional[str] = None
    confidence: Optional[float] = None
    comprehension_score: Optional[float] = None
    next_action: Optional[str] = None
    questions_answered: Optional[int] = None
    correct_answers: Optional[int] = None
    provider_used: Optional[str] = None
    error: Optional[str] = None


# --- Achievement Schemas ---
class AchievementBase(BaseModel):
    name: str
    description: str
    category: str
    points: int
    icon: str = "🏆"  # Default icon if none provided


class AchievementResponse(AchievementBase):
    earned_at: Optional[str] = None
    progress: float = 1.0

    model_config = ConfigDict(from_attributes=True)


class AchievementCreate(BaseModel):
    """Create a custom achievement"""
    name: str
    description: str
    category: str = "custom"
    points: int = 10
    icon: str = "🏆"
    target_user_id: Optional[int] = None  # If set, only this user sees it
    criteria_type: Optional[str] = None
    criteria_value: Optional[float] = None


class AchievementUpdate(BaseModel):
    """Update an achievement"""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    points: Optional[int] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None
    criteria_type: Optional[str] = None
    criteria_value: Optional[float] = None


class AchievementFullResponse(BaseModel):
    """Full achievement details including management info"""
    id: int
    name: str
    description: str
    category: str
    points: int
    icon: str
    is_manual: bool = False
    created_by: Optional[int] = None
    target_user_id: Optional[int] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    criteria_type: Optional[str] = None
    criteria_value: Optional[float] = None

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
    category: Optional[str] = None


class SymbolUsageRequest(BaseModel):
    symbols: List[SymbolUsageItem]
    session_id: Optional[int] = None
    semantic_intent: Optional[str] = None
    context_topic: Optional[str] = None


class NextSymbolRequest(BaseModel):
    current_symbols: str = ""
    chat_history: List[Dict[str, str]] = []
    limit: int = 5
    intent: str = "general"
    offset: int = 0
    board_id: Optional[int] = None


# --- Guardian Profile Schemas (Learning Companion Personality) ---


class MedicalContextSchema(BaseModel):
    """Medical/accessibility context for a student (confidential)"""

    diagnoses: Optional[List[str]] = None
    sensitivities: Optional[List[str]] = None
    accessibility_needs: Optional[List[str]] = None
    notes: Optional[str] = None


class CommunicationStyleSchema(BaseModel):
    """Communication style preferences for the companion"""

    tone: Optional[str] = None  # encouraging, calm, playful, professional
    complexity: Optional[str] = None  # simple, moderate, advanced
    sentence_length: Optional[str] = None  # short, medium, long
    vocabulary_level: Optional[str] = None
    use_emojis: Optional[bool] = None
    avoid_idioms: Optional[bool] = None
    avoid_sarcasm: Optional[bool] = None
    avoid_metaphors: Optional[bool] = None
    explicit_transitions: Optional[bool] = None


class SafetyConstraintsSchema(BaseModel):
    """Safety configuration for content filtering"""

    content_filter_level: Optional[str] = None  # strict, standard, relaxed
    forbidden_topics: Optional[List[str]] = None
    trigger_words: Optional[List[str]] = None
    max_response_length: Optional[int] = None


class CompanionPersonaSchema(BaseModel):
    """Companion persona customization"""

    name: Optional[str] = None
    role: Optional[str] = None
    personality: Optional[List[str]] = None
    greeting_style: Optional[str] = None  # consistent, varied
    sign_off_style: Optional[str] = None


class GuardianProfileCreate(BaseModel):
    """Create a new guardian profile for a student"""

    template_name: str = "default"
    age: Optional[int] = Field(None, ge=1, le=100, description="Student age (1-100)")
    gender: Optional[str] = None
    medical_context: Optional[MedicalContextSchema] = None
    communication_style: Optional[CommunicationStyleSchema] = None
    safety_constraints: Optional[SafetyConstraintsSchema] = None
    companion_persona: Optional[CompanionPersonaSchema] = None
    custom_instructions: Optional[str] = None
    private_notes: Optional[str] = None


class GuardianProfileUpdate(BaseModel):
    """Update an existing guardian profile"""

    template_name: Optional[str] = None
    age: Optional[int] = Field(None, ge=1, le=100, description="Student age (1-100)")
    gender: Optional[str] = None
    medical_context: Optional[MedicalContextSchema] = None
    communication_style: Optional[CommunicationStyleSchema] = None
    safety_constraints: Optional[SafetyConstraintsSchema] = None
    companion_persona: Optional[CompanionPersonaSchema] = None
    custom_instructions: Optional[str] = None
    private_notes: Optional[str] = None
    change_reason: Optional[str] = None  # For audit trail


class GuardianProfileResponse(BaseModel):
    """Guardian profile response with full details"""

    id: int
    user_id: int
    template_name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    medical_context: Optional[dict] = None
    communication_style: Optional[dict] = None
    safety_constraints: Optional[dict] = None
    companion_persona: Optional[dict] = None
    custom_instructions: Optional[str] = None
    private_notes: Optional[str] = None
    is_active: bool = True
    created_by: int
    updated_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProfileHistoryEntry(BaseModel):
    """A single history entry for profile changes"""

    id: int
    field_name: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    changed_by: dict
    changed_at: Optional[str] = None
    change_reason: Optional[str] = None


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
    template_name: Optional[str] = None
    profile_created_at: Optional[str] = None


class SystemPromptPreview(BaseModel):
    """Preview of a rendered system prompt"""

    template_name: str
    prompt: str
