export interface Preferences {
  tts_provider: 'kokoro' | 'browser';
  tts_voice: string;
  tts_local_voice: string;
  tts_local_speed: number;
  ui_language: string;
  notifications_enabled: boolean;
  voice_mode_enabled: boolean;
  dark_mode: boolean;
  dwell_time: number;
  ignore_repeats: number;
  high_contrast: boolean;
  hover_speak_enabled: boolean;
  hover_speak_delay_ms: number;
}

export interface LearningMode {
  id: number;
  name: string;
  key: string;
  description: string;
  prompt_instruction: string;
  is_custom: boolean;
  created_by: number | null;
  // When false, sessions using this mode skip auto-asking questions (the
  // teacher can still request one manually). Absent for legacy data = on.
  auto_ask_enabled?: boolean;
}

export type AiProvider = 'ollama' | 'openrouter' | 'lmstudio' | 'groq';

export interface AiOverride {
  provider?: AiProvider;
  ollama_model?: string;
  openrouter_model?: string;
  lmstudio_model?: string;
  groq_model?: string;
  openrouter_api_key?: string;
  groq_api_key?: string;
  ollama_base_url?: string;
  lmstudio_base_url?: string;
  max_tokens?: number;
  temperature?: number;
}

export interface VoiceStatus {
  stt?: {
    provider?: string;
    installed: boolean;
    model?: string;
    model_loaded?: boolean;
    models?: Record<string, { size: string; description: string; selected?: boolean }>;
  };
  whisper?: { provider?: string; installed: boolean };
  ffmpeg?: { installed?: boolean; available?: boolean; required?: boolean };
  tts?: { provider?: string; client_side?: boolean; installed?: boolean };
  tts_local?: {
    provider?: string;
    installed?: boolean;
    model_present?: boolean;
    available?: boolean;
    model_loaded?: boolean;
    model_size_mb?: number;
    import_error?: string | null;
    download_in_progress?: boolean;
    voices?: Array<{
      name: string;
      language: string;
      gender: 'female' | 'male';
      region?: string | null;
    }>;
  };
  actions?: {
    install_voice?: {
      supported: boolean;
      in_progress?: boolean;
      reason?: string | null;
      platform?: string;
    };
    install_tts?: {
      supported: boolean;
      in_progress?: boolean;
      reason?: string | null;
      platform?: string;
    };
  };
}

export interface ProviderHealth {
  ollama?: { available: boolean; configured?: boolean; reason?: string | null };
  openrouter?: { available: boolean; configured?: boolean; reason?: string | null };
  lmstudio?: { available: boolean; configured?: boolean; reason?: string | null };
  groq?: { available: boolean; configured?: boolean; reason?: string | null };
}
