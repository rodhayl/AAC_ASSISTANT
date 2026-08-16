import { create } from 'zustand'

const LOCAL_VOICE_KEY = 'aac_local_voice'
const USE_LOCAL_KEY = 'aac_use_local_tts'

function readStoredLocalVoice(): string {
  try {
    if (typeof localStorage === 'undefined') return 'default'
    return localStorage.getItem(LOCAL_VOICE_KEY) || 'default'
  } catch {
    return 'default'
  }
}

/** Return the persisted local-TTS toggle, or null when the user never set it. */
export function readStoredUseLocalTTS(): boolean | null {
  try {
    if (typeof localStorage === 'undefined') return null
    const raw = localStorage.getItem(USE_LOCAL_KEY)
    if (raw === null) return null
    return raw === '1'
  } catch {
    return null
  }
}

function writeStoredUseLocalTTS(value: boolean): void {
  try {
    localStorage.setItem(USE_LOCAL_KEY, value ? '1' : '0')
  } catch {
    /* localStorage may be unavailable (private mode/SSR) */
  }
}

interface TTSState {
  selectedVoice: string
  setSelectedVoice: (v: string) => void
  /** Whether the local neural TTS engine is available on the backend. */
  localTTSAvailable: boolean
  setLocalTTSAvailable: (v: boolean) => void
  /** Whether the app should prefer local neural TTS over browser voices. */
  useLocalTTS: boolean
  setUseLocalTTS: (v: boolean) => void
  /**
   * Specific Kokoro voice name used for local neural TTS ('default' = auto).
   * Kept separate from `selectedVoice` (the browser voice) so picking a
   * Kokoro voice never leaks into browser speech or vice versa.
   */
  localVoice: string
  setLocalVoice: (v: string) => void
}

export const useTTSStore = create<TTSState>((set) => ({
  selectedVoice: 'default',
  setSelectedVoice: (v) => set({ selectedVoice: v }),
  localTTSAvailable: false,
  setLocalTTSAvailable: (v) => set({ localTTSAvailable: v }),
  useLocalTTS: readStoredUseLocalTTS() ?? false,
  setUseLocalTTS: (v) => {
    writeStoredUseLocalTTS(v)
    set({ useLocalTTS: v })
  },
  localVoice: readStoredLocalVoice(),
  setLocalVoice: (v) => {
    try {
      localStorage.setItem(LOCAL_VOICE_KEY, v)
    } catch {
      /* localStorage may be unavailable (private mode/SSR) */
    }
    set({ localVoice: v })
  },
}))
