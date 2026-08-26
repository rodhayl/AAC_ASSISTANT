import { create } from 'zustand'

const LOCAL_VOICE_KEY = 'aac_local_voice'

function readStoredLocalVoice(): string {
  try {
    if (typeof localStorage === 'undefined') return 'default'
    return localStorage.getItem(LOCAL_VOICE_KEY) || 'default'
  } catch {
    return 'default'
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
  ttsWarmupStatus: 'idle',
  setTTSWarmupStatus: (v) => set({ ttsWarmupStatus: v }),
  speechWarmupStatus: 'idle',
  setSpeechWarmupStatus: (v) => set({ speechWarmupStatus: v }),
  vectorWarmupStatus: 'idle',
  setVectorWarmupStatus: (v) => set({ vectorWarmupStatus: v }),
}))
