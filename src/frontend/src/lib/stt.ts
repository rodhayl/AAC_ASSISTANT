import { config } from '../config'
import { useAuthStore } from '../store/authStore'

// ---------------------------------------------------------------------------
// Local speech-to-text (backend faster-whisper) capability
// ---------------------------------------------------------------------------
// The backend transcribes uploaded audio with the optional faster-whisper
// extra. When it is missing (503), callers fall back to the browser's
// SpeechRecognition API. The probe is cached so repeated opens do not re-hit
// /providers/voice-status.

let capabilityChecked = false
let localSTTAvailable = false

export function isLocalSTTAvailable(): boolean {
  return localSTTAvailable
}

export async function refreshLocalSTTCapability(): Promise<boolean> {
  try {
    const res = await fetch(`${config.API_BASE_URL}/providers/voice-status`, {
      headers: { Authorization: `Bearer ${useAuthStore.getState().token || ''}` },
      signal: AbortSignal.timeout(5000),
    })
    localSTTAvailable = res.ok ? Boolean((await res.json())?.stt?.available) : false
  } catch {
    localSTTAvailable = false
  } finally {
    capabilityChecked = true
  }
  return localSTTAvailable
}

/** Probe the backend once and return whether local STT can transcribe audio. */
export function initLocalSTT(): Promise<boolean> {
  if (capabilityChecked) return Promise.resolve(localSTTAvailable)
  return refreshLocalSTTCapability()
}

/**
 * Transcribe a recorded audio blob with the local backend engine.
 *
 * Uploads directly (not through the offline-aware axios client) because a
 * transient audio clip must never be queued for replay after reconnection.
 */
export async function transcribeAudio(blob: Blob, lang: string): Promise<string> {
  const token = useAuthStore.getState().token || ''
  const formData = new FormData()
  formData.append('file', blob, 'recording.webm')
  const langQuery = encodeURIComponent((lang || 'es').split('-')[0] || 'es')
  const res = await fetch(`${config.API_BASE_URL}/providers/transcribe?lang=${langQuery}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  if (!res.ok) {
    throw new Error(`Transcription failed with status ${res.status}`)
  }
  const data = await res.json()
  return typeof data?.text === 'string' ? data.text : ''
}
