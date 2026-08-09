type Status = 'idle' | 'speaking'

interface EnqueueOptions {
  key?: string | number
  rate?: number
  pitch?: number
  lang?: string
}

const NO_START_WATCHDOG_MS = 1_500
const SPEAKING_WATCHDOG_MS = 15_000
// Allow extra time for the first local synthesis (model warm-up + network).
const LOCAL_START_WINDOW_MS = 12_000

// Voices load asynchronously in Chrome/Edge; cache them and refresh on the
// voiceschanged event so speech never uses an empty voice list on first use.
let cachedVoices: SpeechSynthesisVoice[] = []
let voicesListenerAttached = false

function refreshCachedVoices() {
  if ('speechSynthesis' in window) {
    cachedVoices = window.speechSynthesis.getVoices() || []
  }
}

function getCachedVoices(): SpeechSynthesisVoice[] {
  if (cachedVoices.length === 0) refreshCachedVoices()
  return cachedVoices
}

function ensureVoicesListener() {
  if (voicesListenerAttached || !('speechSynthesis' in window)) return
  voicesListenerAttached = true
  refreshCachedVoices()
  window.speechSynthesis.addEventListener?.('voiceschanged', refreshCachedVoices)
}

/**
 * Pick the best available voice for the requested preference and locale.
 *
 * Order of preference:
 *  1. Exact voiceURI/name match (user explicitly selected it in Settings)
 *  2. A voice whose lang matches the active UI locale (prefer exact prefix)
 *  3. Any voice of the same language, honoring female/male preference
 *  4. null (caller falls back to browser default for the locale)
 */
function pickBestVoice(pref: string, locale: string): SpeechSynthesisVoice | null {
  ensureVoicesListener()
  const voices = getCachedVoices()
  if (voices.length === 0) return null

  // 1. Exact match on the stored preference (voiceURI or display name)
  if (pref && pref !== 'default' && pref !== 'female' && pref !== 'male') {
    const exact = voices.find(v => v.voiceURI === pref || v.name === pref)
    if (exact) return exact
  }

  const baseLang = (locale || 'en').split('-')[0].toLowerCase()
  const langRe = new RegExp(`^${baseLang}(-|$)`, 'i')

  const femalePref = pref === 'female'
  const malePref = pref === 'male'

  // 2. Best exact-locale match, then any same-language voice. Prefer a gender
  //    that matches the requested voice style when one was specified.
  const gendered = voices.filter(v =>
    langRe.test(v.lang) && (femalePref ? /female/i.test(v.name) : malePref ? /male/i.test(v.name) : true)
  )
  const candidates = gendered.length > 0 ? gendered : voices.filter(v => langRe.test(v.lang))
  if (candidates.length === 0) return null

  // Prefer the voice that most closely matches the full locale (es-ES over es-MX)
  // and prefer voices with an explicit region, then stable ordering.
  const localePrefix = locale.toLowerCase()
  const exactLocale = candidates.find(v => v.lang.toLowerCase() === localePrefix)
  if (exactLocale) return exactLocale
  return candidates.sort((a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name))[0]
}

// ---------------------------------------------------------------------------
// Local neural TTS (backend Kokoro) capability
// ---------------------------------------------------------------------------
// When enabled, the queue requests synthesized audio from the backend and
// plays it with an <audio> element. Any failure degrades to the browser's
// SpeechSynthesis voices, so the feature is purely additive. The enable/flag
// state lives in the TTS store so Settings and the queue share one source.
let capabilityChecked = false

async function checkLocalTTSCapability(): Promise<boolean> {
  try {
    const res = await fetch(`${config.API_BASE_URL}/providers/voice-status`, {
      headers: { Authorization: `Bearer ${useAuthStore.getState().token || ''}` },
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok) return false
    const data = await res.json()
    return Boolean(data?.tts_local?.available)
  } catch {
    return false
  }
}

async function refreshLocalTTSCapability() {
  const available = await checkLocalTTSCapability()
  const store = useTTSStore.getState()
  // Defensive: some tests/exports may provide a partial store mock.
  if (typeof store.setLocalTTSAvailable === 'function') {
    store.setLocalTTSAvailable(available)
  }
  if (typeof store.setUseLocalTTS === 'function') {
    store.setUseLocalTTS(available)
  }
  capabilityChecked = true
}

/** Probe the backend once (cached) and enable local TTS when available. */
export function initLocalTTS() {
  if (capabilityChecked) return
  void refreshLocalTTSCapability()
}

class TTSQueue {
  private queue: Array<{ text: string; opts: EnqueueOptions }>
  private status: Status
  private listeners: Array<(s: Status) => void>
  private lastSpokenAt: Map<string | number, number>
  private debounceMs: number
  private activeUtteranceId: number | null
  private nextUtteranceId: number
  private speakingRequestedAt: number | null
  private speakingStartedAt: number | null
  private noStartWatchdog: ReturnType<typeof setTimeout> | null
  private speakingWatchdog: ReturnType<typeof setTimeout> | null
  private localAudio: HTMLAudioElement | null
  private localAudioUrl: string | null
  private localStartWatchdog: ReturnType<typeof setTimeout> | null
  private localSynthesisCleanup: (() => void) | null

  constructor() {
    this.queue = []
    this.status = 'idle'
    this.listeners = []
    this.lastSpokenAt = new Map()
    this.debounceMs = 250
    this.activeUtteranceId = null
    this.nextUtteranceId = 0
    this.speakingRequestedAt = null
    this.speakingStartedAt = null
    this.noStartWatchdog = null
    this.speakingWatchdog = null
    this.localAudio = null
    this.localAudioUrl = null
    this.localStartWatchdog = null
    this.localSynthesisCleanup = null
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
  }

  onStatusChange(cb: (s: Status) => void) {
    this.listeners.push(cb)
    return () => {
      this.listeners = this.listeners.filter(l => l !== cb)
    }
  }

  getStatus(): Status {
    return this.status
  }

  private setStatus(s: Status) {
    this.status = s
    for (const l of this.listeners) l(s)
  }

  cancelAll() {
    this.queue = []
    this.clearWatchdogs()
    this.activeUtteranceId = null
    this.speakingRequestedAt = null
    this.speakingStartedAt = null
    this.clearLocalSynthesisAttempt()
    this.stopLocalAudio()
    if ('speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel()
      } catch { /* browser may not support cancel */ }
    }
    this.setStatus('idle')
  }

  enqueue(text: string, opts: EnqueueOptions = {}) {
    const now = Date.now()
    const k = opts.key ?? text
    const last = this.lastSpokenAt.get(k) || 0
    if (now - last < this.debounceMs) return
    this.lastSpokenAt.set(k, now)

    // Probe the backend for local neural TTS on first use (lazy, non-blocking).
    initLocalTTS()

    this.queue.push({ text, opts })
    this.processNext()
  }

  private processNext() {
    if (this.activeUtteranceId !== null) {
      if (this.status !== 'speaking' || !this.isWatchdogExpired()) return
      this.finishCurrentUtterance(true)
    }

    if (this.queue.length === 0) {
      this.setStatus('idle')
      return
    }
    const item = this.queue.shift()!
    if (!('speechSynthesis' in window) && typeof Audio === 'undefined') {
      this.setStatus('idle')
      return
    }

    const utteranceId = ++this.nextUtteranceId
    this.activeUtteranceId = utteranceId
    this.speakingRequestedAt = Date.now()
    this.speakingStartedAt = null

    // Reflect requested speaking state immediately; the local path or the
    // no-start watchdog takes over from here.
    this.setStatus('speaking')

    if (useTTSStore.getState().useLocalTTS && useTTSStore.getState().localTTSAvailable) {
      void this.speakLocalWithFallback(item, utteranceId)
    } else {
      this.scheduleNoStartWatchdog(utteranceId)
      this.speakViaBrowser(item, utteranceId)
    }
  }

  /**
   * Try the local neural TTS engine; if it cannot synthesize within the
   * start window, fall back to the browser's SpeechSynthesis voices.
   */
  private async speakLocalWithFallback(
    item: { text: string; opts: EnqueueOptions },
    utteranceId: number,
  ) {
    // Once the browser path has taken over (or the local attempt was
    // abandoned) any late fetch/audio result must be ignored to avoid
    // speaking twice or restarting an in-flight utterance.
    let localAbandoned = false
    let synthesisController: AbortController | null = null
    let synthesisTimeout: ReturnType<typeof setTimeout> | null = null

    const clearSynthesisRequest = () => {
      if (synthesisTimeout !== null) {
        clearTimeout(synthesisTimeout)
        synthesisTimeout = null
      }
      synthesisController?.abort()
      synthesisController = null
      if (this.localSynthesisCleanup === clearSynthesisRequest) {
        this.localSynthesisCleanup = null
      }
    }
    this.localSynthesisCleanup = clearSynthesisRequest

    const fallback = () => {
      if (localAbandoned || !this.isActiveUtterance(utteranceId)) return
      localAbandoned = true
      this.clearLocalStartWatchdog(localStartWatchdog)
      clearSynthesisRequest()
      this.stopLocalAudio()
      this.clearNoStartWatchdog()
      this.speakViaBrowser(item, utteranceId)
    }

    const localStartWatchdog = setTimeout(() => {
      if (this.localStartWatchdog === localStartWatchdog) {
        this.localStartWatchdog = null
      }
      fallback()
    }, LOCAL_START_WINDOW_MS)
    this.localStartWatchdog = localStartWatchdog

    try {
      const lang = item.opts.lang || i18n.language || 'es'
      const baseLang = lang.split('-')[0]
      // The local engine uses its own voice selection (specific Kokoro voice
      // names); `selectedVoice` remains the browser voice used by
      // speakViaBrowser so the two paths never interfere.
      const voicePref = useTTSStore.getState().localVoice
      const token = useAuthStore.getState().token || ''

      const controller = new AbortController()
      synthesisController = controller
      synthesisTimeout = setTimeout(() => controller.abort(), LOCAL_START_WINDOW_MS)
      const res = await fetch(`${config.API_BASE_URL}/providers/tts/synthesize`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          text: item.text,
          lang: baseLang,
          voice: voicePref || 'default',
          speed: item.opts.rate || 1.0,
        }),
        signal: controller.signal,
      })
      clearSynthesisRequest()
      if (localAbandoned) return
      if (!res.ok) {
        fallback()
        return
      }

      const blob = await res.blob()
      if (localAbandoned || !this.isActiveUtterance(utteranceId)) return

      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      this.localAudio = audio
      this.localAudioUrl = url

      const cleanupAudio = () => {
        if (this.localAudio === audio) this.localAudio = null
        if (this.localAudioUrl === url) {
          URL.revokeObjectURL(url)
          this.localAudioUrl = null
        }
      }

      audio.onended = () => {
        cleanupAudio()
        if (localAbandoned || !this.isActiveUtterance(utteranceId)) return
        this.clearLocalStartWatchdog(localStartWatchdog)
        this.finishCurrentUtterance(false)
        Promise.resolve().then(() => this.processNext())
      }
      audio.onerror = () => {
        cleanupAudio()
        if (localAbandoned || !this.isActiveUtterance(utteranceId)) return
        this.clearLocalStartWatchdog(localStartWatchdog)
        this.finishCurrentUtterance(false)
        Promise.resolve().then(() => this.processNext())
      }

      await audio.play()
      if (localAbandoned) {
        cleanupAudio()
        return
      }
      if (!this.isActiveUtterance(utteranceId)) return
      // Playback started: promote to the normal speaking watchdog. Use the
      // audio's real duration so long sentences are not cut off early.
      this.clearLocalStartWatchdog(localStartWatchdog)
      this.speakingStartedAt = Date.now()
      this.clearNoStartWatchdog()
      const durationMs = Number.isFinite(audio.duration) ? audio.duration * 1000 : 0
      this.scheduleSpeakingWatchdog(utteranceId, Math.max(SPEAKING_WATCHDOG_MS, durationMs + 3_000))
    } catch {
      this.clearLocalStartWatchdog(localStartWatchdog)
      clearSynthesisRequest()
      if (!localAbandoned) fallback()
    }
  }

  private clearLocalStartWatchdog(watchdog: ReturnType<typeof setTimeout>) {
    clearTimeout(watchdog)
    if (this.localStartWatchdog === watchdog) {
      this.localStartWatchdog = null
    }
  }

  private clearLocalSynthesisAttempt() {
    if (this.localStartWatchdog !== null) {
      clearTimeout(this.localStartWatchdog)
      this.localStartWatchdog = null
    }
    const cleanup = this.localSynthesisCleanup
    this.localSynthesisCleanup = null
    cleanup?.()
  }

  private stopLocalAudio() {
    if (this.localAudio) {
      try {
        this.localAudio.pause()
        this.localAudio.src = ''
      } catch { /* ignore */ }
      this.localAudio = null
    }
    if (this.localAudioUrl) {
      URL.revokeObjectURL(this.localAudioUrl)
      this.localAudioUrl = null
    }
  }

  private speakViaBrowser(
    item: { text: string; opts: EnqueueOptions },
    utteranceId: number,
  ) {
    if (!('speechSynthesis' in window)) {
      if (this.isActiveUtterance(utteranceId)) {
        this.finishCurrentUtterance(false)
        Promise.resolve().then(() => this.processNext())
      }
      return
    }

    try {
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(item.text)
      if (item.opts.rate) u.rate = item.opts.rate
      if (item.opts.pitch) u.pitch = item.opts.pitch
      if (item.opts.lang) u.lang = item.opts.lang
      try {
        const pref = useTTSStore.getState().selectedVoice
        const currentLocale = i18n.language || 'es'
        const chosen = pickBestVoice(pref, currentLocale)

        if (chosen) {
          u.voice = chosen
          u.lang = chosen.lang // Use the voice's language
        } else {
          // No matching-language voice installed. Ask the browser for the
          // active locale anyway; Chromium picks its best voice for it, and
          // never let the utterance silently fall back to a foreign voice.
          u.lang = currentLocale || (i18n.language || 'es')
        }
      } catch { /* voice selection not critical */ }

      u.onend = () => {
        if (!this.isActiveUtterance(utteranceId)) return
        this.finishCurrentUtterance(false)
        // Continue with next queued item
        // Use microtask to avoid re-entrancy issues
        Promise.resolve().then(() => this.processNext())
      }
      u.onerror = () => {
        if (!this.isActiveUtterance(utteranceId)) return
        this.finishCurrentUtterance(false)
        Promise.resolve().then(() => this.processNext())
      }

      u.onstart = () => {
        if (!this.isActiveUtterance(utteranceId)) return
        this.speakingStartedAt = Date.now()
        this.clearNoStartWatchdog()
        this.scheduleSpeakingWatchdog(utteranceId)
        this.setStatus('speaking')
      }
      window.speechSynthesis.speak(u)
      if (this.isActiveUtterance(utteranceId)) {
        // Some speech synthesis implementations never emit onstart. Reflect the
        // requested speaking state immediately and let the no-start watchdog
        // recover if the browser silently ignores the utterance.
        this.setStatus('speaking')
        if (this.speakingStartedAt === null) {
          this.scheduleNoStartWatchdog(utteranceId)
        }
      }
    } catch {
      if (this.isActiveUtterance(utteranceId)) {
        this.finishCurrentUtterance(false)
        Promise.resolve().then(() => this.processNext())
      }
    }
  }

  private isActiveUtterance(utteranceId: number) {
    return this.activeUtteranceId === utteranceId
  }

  private isWatchdogExpired() {
    if (this.status !== 'speaking' || this.activeUtteranceId === null) return false

    const startedAt = this.speakingStartedAt ?? this.speakingRequestedAt
    if (startedAt === null) return false

    const limit = this.speakingStartedAt === null
      ? NO_START_WATCHDOG_MS
      : SPEAKING_WATCHDOG_MS
    return Date.now() - startedAt >= limit
  }

  private scheduleNoStartWatchdog(utteranceId: number) {
    this.clearNoStartWatchdog()
    this.noStartWatchdog = setTimeout(() => {
      if (!this.isActiveUtterance(utteranceId) || this.speakingStartedAt !== null) return
      this.finishCurrentUtterance(true)
      this.processNext()
    }, NO_START_WATCHDOG_MS)
  }

  private scheduleSpeakingWatchdog(utteranceId: number, limitMs: number = SPEAKING_WATCHDOG_MS) {
    this.clearSpeakingWatchdog()
    this.speakingWatchdog = setTimeout(() => {
      if (!this.isActiveUtterance(utteranceId)) return
      this.finishCurrentUtterance(true)
      this.processNext()
    }, limitMs)
  }

  private clearNoStartWatchdog() {
    if (this.noStartWatchdog !== null) {
      clearTimeout(this.noStartWatchdog)
      this.noStartWatchdog = null
    }
  }

  private clearSpeakingWatchdog() {
    if (this.speakingWatchdog !== null) {
      clearTimeout(this.speakingWatchdog)
      this.speakingWatchdog = null
    }
  }

  private clearWatchdogs() {
    this.clearNoStartWatchdog()
    this.clearSpeakingWatchdog()
  }

  private finishCurrentUtterance(cancelSpeech: boolean) {
    this.clearWatchdogs()
    this.activeUtteranceId = null
    this.speakingRequestedAt = null
    this.speakingStartedAt = null
    this.clearLocalSynthesisAttempt()
    this.stopLocalAudio()
    if (cancelSpeech && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel()
      } catch { /* browser may not support cancel */ }
    }
    this.setStatus('idle')
  }
}

export const tts = new TTSQueue()
import { useTTSStore } from '../store/ttsStore'
import { useAuthStore } from '../store/authStore'
import i18n from '../i18n/index'
import { config } from '../config'
