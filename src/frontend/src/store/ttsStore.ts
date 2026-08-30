import { create } from 'zustand'

const LOCAL_VOICE_KEY = 'aac_local_voice'
const LOCAL_SPEED_KEY = 'aac_local_speed'

// Kokoro synthesis accepts speeds in [0.5, 2.0] (see providers.py).
export const LOCAL_SPEED_MIN = 0.5
export const LOCAL_SPEED_MAX = 2.0

export function clampLocalSpeed(value: number): number {
  if (!Number.isFinite(value)) return 1.0
  return Math.min(Math.max(value, LOCAL_SPEED_MIN), LOCAL_SPEED_MAX)
}

function readStoredLocalVoice(): string {
  try {
    if (typeof localStorage === 'undefined') return 'default'
    return localStorage.getItem(LOCAL_VOICE_KEY) || 'default'
  } catch {
    return 'default'
  }
}

function readStoredLocalSpeed(): number {
  try {
    if (typeof localStorage === 'undefined') return 1.0
    return clampLocalSpeed(parseFloat(localStorage.getItem(LOCAL_SPEED_KEY) || ''))
  } catch {
    return 1.0
  }
}

export type WarmupStatus = 'idle' | 'warming' | 'ready' | 'unavailable'

interface TTSState {
  ttsProvider: 'kokoro' | 'browser'
  setTTSProvider: (provider: 'kokoro' | 'browser') => void
  selectedVoice: string
  setSelectedVoice: (v: string) => void
  /** Whether the local neural TTS engine is available on the backend. */
  localTTSAvailable: boolean
  setLocalTTSAvailable: (v: boolean) => void
  /**
   * Specific Kokoro voice name used for local neural TTS ('default' = auto).
   * Kept separate from `selectedVoice` (the browser voice) so picking a
   * Kokoro voice never leaks into browser speech or vice versa.
   */
  localVoice: string
  setLocalVoice: (v: string) => void
  /**
   * Base speaking speed for local neural TTS (1.0 = normal). Per-message
   * rate modifiers multiply this base; the result is clamped to the
   * Kokoro-supported range before synthesis.
   */
  localSpeed: number
  setLocalSpeed: (v: number) => void
  /** Background pre-load status of the backend Kokoro TTS model. */
  ttsWarmupStatus: WarmupStatus
  setTTSWarmupStatus: (v: WarmupStatus) => void
  /** Background pre-load status of the backend faster-whisper STT model. */
  speechWarmupStatus: WarmupStatus
  setSpeechWarmupStatus: (v: WarmupStatus) => void
  /** Background pre-load status of the fastembed semantic search index. */
  vectorWarmupStatus: WarmupStatus
  setVectorWarmupStatus: (v: WarmupStatus) => void
}

export const useTTSStore = create<TTSState>((set) => ({
  ttsProvider: 'kokoro',
  setTTSProvider: (provider) => set({ ttsProvider: provider }),
  selectedVoice: 'default',
  setSelectedVoice: (v) => set({ selectedVoice: v }),
  localTTSAvailable: false,
  setLocalTTSAvailable: (v) => set({ localTTSAvailable: v }),
  localVoice: readStoredLocalVoice(),
  setLocalVoice: (v) => {
    try {
      localStorage.setItem(LOCAL_VOICE_KEY, v)
    } catch {
      /* localStorage may be unavailable (private mode/SSR) */
    }
    set({ localVoice: v })
  },
  localSpeed: readStoredLocalSpeed(),
  setLocalSpeed: (v) => {
    const speed = clampLocalSpeed(v)
    try {
      localStorage.setItem(LOCAL_SPEED_KEY, String(speed))
    } catch {
      /* localStorage may be unavailable (private mode/SSR) */
    }
    set({ localSpeed: speed })
  },
  ttsWarmupStatus: 'idle',
  setTTSWarmupStatus: (v) => set({ ttsWarmupStatus: v }),
  speechWarmupStatus: 'idle',
  setSpeechWarmupStatus: (v) => set({ speechWarmupStatus: v }),
  vectorWarmupStatus: 'idle',
  setVectorWarmupStatus: (v) => set({ vectorWarmupStatus: v }),
}))
