import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { UserPreferences, UserPreferencesResponse } from '../types';
import { config } from '../config';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// The UI offers regional codes (es-ES / en-US), but the language switcher and
// legacy rows may persist short codes (es / en). Normalize so a stored value
// always matches one of the <select> options regardless of how it was saved.
export function normalizeUILanguage(code: string | null | undefined): string {
  const lang = (code || '').trim().toLowerCase();
  if (lang.startsWith('en')) return 'en-US';
  if (lang.startsWith('es')) return 'es-ES';
  return lang || 'es-ES';
}

/**
 * Map the preferences wire shape into the typed store contract in one place.
 *
 * The backend already guarantees sane persisted values
 * (build_preferences_response in src/api/routers/auth_helpers.py fills
 * tts_voice/tts_local_voice with "default", clamps a garbage tts_provider to
 * "kokoro" and a garbage ui_language to "es-ES", and defaults null booleans
 * to their documented on/off values). A response can still carry explicit
 * NULLs for the optional language fields, so these defaults deliberately
 * mirror that backend builder — the GET hydration path and the PUT
 * updateAuthSettings handler share this function so the two cannot silently
 * drift apart again (they previously disagreed on tts_language).
 */
export function normalizePreferencesResponse(
  data: UserPreferencesResponse,
): UserPreferences {
  return {
    tts_provider: data.tts_provider === 'browser' ? 'browser' : 'kokoro',
    tts_voice: data.tts_voice || 'default',
    tts_local_voice: data.tts_local_voice || 'default',
    tts_local_speed: data.tts_local_speed ?? 1.0,
    tts_language: data.tts_language ?? 'en',
    ui_language: normalizeUILanguage(data.ui_language),
    notifications_enabled: data.notifications_enabled ?? true,
    voice_mode_enabled: data.voice_mode_enabled ?? true,
    dark_mode: data.dark_mode ?? false,
    dwell_time: data.dwell_time ?? 0,
    ignore_repeats: data.ignore_repeats ?? 0,
    high_contrast: data.high_contrast ?? false,
    hover_speak_enabled: data.hover_speak_enabled ?? false,
    hover_speak_delay_ms: data.hover_speak_delay_ms ?? 1000,
    default_learning_mode: data.default_learning_mode || 'practice',
  };
}

export function assetUrl(path?: string) {
  if (!path) return '';
  if (path.startsWith('/uploads')) return `${config.BACKEND_URL}${path}`;
  return path;
}
