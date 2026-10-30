export interface UserPreferences {
  tts_voice: string;
  tts_language: string;
  ui_language: string;
  notifications_enabled: boolean;
  voice_mode_enabled: boolean;
  dark_mode: boolean;
  dwell_time: number;
  ignore_repeats: number;
  high_contrast: boolean;
}

export interface User {
  id: number;
  username: string;
  email?: string;
  display_name: string;
  user_type: 'student' | 'teacher' | 'admin';
  is_active: boolean;
  created_at: string;
  settings?: UserPreferences;
}

export interface Symbol {
  id: number;
  label: string;
  description?: string;
  category: string;
  image_path?: string;
  audio_path?: string;
  keywords?: string;
  language: string;
  is_builtin: boolean;
  created_at: string;
  is_in_use?: boolean;
}

export interface BoardSymbol {
  id: number;
  symbol_id: number;
  position_x: number;
  position_y: number;
  size: number;
  is_visible: boolean;
  custom_text?: string;
  color?: string;
  linked_board_id?: number | null;
  symbol: Symbol;
}

export interface Board {
  id: number;
  user_id: number;
  name: string;
  description?: string;
  category: string;
  is_public: boolean;
  is_template: boolean;
  created_at: string;
  updated_at: string;
  symbols: BoardSymbol[];
  grid_rows?: number;
  grid_cols?: number;
  ai_enabled?: boolean;
  ai_provider?: string;
  ai_model?: string;
  playable_symbols_count?: number;
  locale?: string;
  is_language_learning?: boolean;
}
// Ensure Board is exported


export interface Achievement {
  name: string;
  description: string;
  category: string;
  points: number;
  icon: string;
  earned_at?: string;
  progress: number;
}

export interface AchievementFull extends Achievement {
  id: number;
  is_manual?: boolean;
  created_by?: number | null;
  target_user_id?: number | null;
  is_active?: boolean;
  created_at?: string;
  criteria_type?: string | null;
  criteria_value?: number | null;
}

export interface LeaderboardEntry {
  username: string;
  display_name: string;
  points: number;
  achievement_count: number;
}

export interface LearningSessionStart {
  topic: string;
  purpose?: string;
  difficulty: string;
  board_id?: number;
}

export interface LearningSessionResponse {
  success: boolean;
  session_id: number;
  plan_id?: number;
  task_id?: number;
  board_id?: number;
  welcome_message?: string;
  topic?: string;
  difficulty?: string;
  error?: string;
}

export interface MedicalContext {
  diagnoses?: string[];
  sensitivities?: string[];
  accessibility_needs?: string[];
  notes?: string;
}

export interface CommunicationStyle {
  tone?: string;
  complexity?: string;
  sentence_length?: string;
  vocabulary_level?: string;
  use_emojis?: boolean;
  avoid_idioms?: boolean;
  avoid_sarcasm?: boolean;
  avoid_metaphors?: boolean;
  explicit_transitions?: boolean;
}

export interface SafetyConstraints {
  content_filter_level?: string;
  forbidden_topics?: string[];
  trigger_words?: string[];
  max_response_length?: number;
}

export interface CompanionPersona {
  name?: string;
  role?: string;
  personality?: string[];
  greeting_style?: string;
  sign_off_style?: string;
}

export interface GuardianProfile {
  id: number;
  user_id: number;
  template_name: string;
  age?: number;
  gender?: string;
  medical_context?: MedicalContext;
  communication_style?: CommunicationStyle;
  safety_constraints?: SafetyConstraints;
  companion_persona?: CompanionPersona;
  custom_instructions?: string;
  private_notes?: string;
  is_active: boolean;
  created_by: number;
  updated_by?: number;
  created_at?: string;
  updated_at?: string;
}

export interface TemplateInfo {
  name: string;
  display_name: string;
  description: string;
  version: string;
}

export interface QuestionResponse {
  success: boolean;
  question_id?: number;
  question_text?: string;
  question?: string;  // Alias for question_text
  choices?: string[];
  difficulty?: string;
  correct_answer_index?: number;
  message?: string;  // Generic message field
  error?: string;
  full_thinking?: string;  // Admin debug field
}

export interface AnswerSubmit {
  answer: string;
  is_voice: boolean;
}

export interface AnswerResponse {
  success: boolean;
  is_correct?: boolean;
  transcription?: string;
  feedback_message?: string;
  assistant_reply?: string;  // LLM response field
  encouraging_feedback?: string;  // Feedback field
  message?: string;  // Generic message field
  confidence?: number;
  comprehension_score?: number;
  next_action?: string;
  questions_answered?: number;
  correct_answers?: number;
  error?: string;
  full_thinking?: string;  // Admin debug field
}
