type Status = 'idle' | 'speaking'

interface EnqueueOptions {
  key?: string | number
  rate?: number
  pitch?: number
  lang?: string
}

const NO_START_WATCHDOG_MS = 1_500
const SPEAKING_WATCHDOG_MS = 15_000
// Allow local synthesis enough time for a cold model load plus generation.
const LOCAL_START_WINDOW_MS = 60_000
const SILENT_AUDIO_DATA_URI =
  'data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'

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
  capabilityChecked = true
}

// ---------------------------------------------------------------------------
// Lazy background warm-up
// ---------------------------------------------------------------------------
// The first utterance pays two one-time costs: the voice-status capability
// round-trip and, with local neural TTS, the backend Kokoro model load. The
// first voice answer additionally pays the faster-whisper model load. Warm
// every lazy backend model in one batched request when the authenticated app
// shell mounts so the first spoken message in a conversation (and the first
// microphone answer) starts immediately.
let warmupStarted = false

function setWarmupStatus(kind: 'tts' | 'speech' | 'vector', status: WarmupStatus) {
  const store = useTTSStore.getState()
  const setter = kind === 'tts'
    ? store.setTTSWarmupStatus
    : kind === 'speech'
      ? store.setSpeechWarmupStatus
      : store.setVectorWarmupStatus
  // Defensive: some tests/exports may provide a partial store mock.
  if (typeof setter === 'function') setter(status)
}

export function warmup() {
  // Prepare browser voices early: Chrome/Edge populate getVoices() asynchron-
  // ously, so starting the listener now avoids an empty voice list on first
  // use of the browser speech path too.
  ensureVoicesListener()
  if (warmupStarted) return
  warmupStarted = true
  void (async () => {
    // Browser-only speech users skip the Kokoro model load (a ~325MB
    // resident model they would never use), but faster-whisper still
    // pre-loads: the microphone path is independent of the TTS provider.
    // The fastembed semantic index pre-loads for everyone because the
    // symbol search does not depend on the TTS provider setting.
    let targets = useTTSStore.getState().ttsProvider === 'kokoro'
      ? ['tts', 'speech', 'vector']
      : ['speech', 'vector']
    try {
      if (targets.includes('tts')) {
        if (!capabilityChecked) {
          await refreshLocalTTSCapability()
        }
        if (!useTTSStore.getState().localTTSAvailable) {
          // The TTS engine is unavailable: drop the target instead of
          // returning, so the batch still pre-loads the other lazy models
          // (the standalone speech warm-up used to run regardless).
          setWarmupStatus('tts', 'unavailable')
          targets = targets.filter((target) => target !== 'tts')
        } else {
          setWarmupStatus('tts', 'warming')
        }
      }
      setWarmupStatus('speech', 'warming')
      setWarmupStatus('vector', 'warming')
      // One batched request pre-loads every lazy backend model; each target
      // reports independently so an unavailable target never hides another.
      // The request completes once each model is resident (or unavailable),
      // so it doubles as the pre-load status signal; nothing blocks on it
      // from the caller's side.
      const res = await fetch(`${config.API_BASE_URL}/providers/warmup`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${useAuthStore.getState().token || ''}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ targets }),
      })
      let data: Record<string, { warmed?: boolean }> = {}
      try {
        data = (await res.json()) as Record<string, { warmed?: boolean }>
      } catch { /* non-JSON body */ }
      if (res.ok) {
        if (targets.includes('tts')) {
          setWarmupStatus('tts', data.tts?.warmed ? 'ready' : 'unavailable')
        }
        setWarmupStatus('speech', data.speech?.warmed ? 'ready' : 'unavailable')
        setWarmupStatus('vector', data.vector?.warmed ? 'ready' : 'unavailable')
      } else {
        if (targets.includes('tts')) setWarmupStatus('tts', 'unavailable')
        setWarmupStatus('speech', 'unavailable')
        setWarmupStatus('vector', 'unavailable')
      }
    } catch {
      // Best-effort: the first enqueue re-checks capability as usual.
      if (targets.includes('tts')) setWarmupStatus('tts', 'unavailable')
      setWarmupStatus('speech', 'unavailable')
      setWarmupStatus('vector', 'unavailable')
    }
  })()
}

class TTSQueue {
  private queue: Array<{ text: string; opts: EnqueueOptions }>
  private status: Status
  private listeners: Array<(s: Status) => void>
  private lastSpokenAt: Map<string | number, number>
  private debounceMs: number
  private activeUtteranceId: number | null
  private activeIsLocal: boolean
  private nextUtteranceId: number
  private speakingRequestedAt: number | null
  private speakingStartedAt: number | null
  private noStartWatchdog: ReturnType<typeof setTimeout> | null
  private speakingWatchdog: ReturnType<typeof setTimeout> | null
  private localAudio: HTMLAudioElement | null
  private localAudioUrl: string | null
  private localAudioElement: HTMLAudioElement | null
  private localStartWatchdog: ReturnType<typeof setTimeout> | null
  private localSynthesisCleanup: (() => void) | null
  private unlockedAudio: HTMLAudioElement | null

  constructor() {
    this.queue = []
    this.status = 'idle'
    this.listeners = []
    this.lastSpokenAt = new Map()
    this.debounceMs = 250
    this.activeUtteranceId = null
    this.activeIsLocal = false
    this.nextUtteranceId = 0
    this.speakingRequestedAt = null
    this.speakingStartedAt = null
    this.noStartWatchdog = null
    this.speakingWatchdog = null
    this.localAudio = null
    this.localAudioUrl = null
    this.localAudioElement = null
    this.localStartWatchdog = null
    this.localSynthesisCleanup = null
    this.unlockedAudio = null
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
  }

  unlock() {
    if (this.unlockedAudio || typeof window === 'undefined' || typeof window.Audio === 'undefined') return

    const audio = new window.Audio(SILENT_AUDIO_DATA_URI)
    audio.muted = true
    audio.volume = 0
    this.unlockedAudio = audio
    void audio.play().catch(() => {
      if (this.unlockedAudio === audio) {
        this.unlockedAudio = null
      }
    })
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
    this.activeIsLocal = false
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

    this.queue.push({ text, opts })
    this.processNext()
  }

  private processNext() {
    if (this.activeUtteranceId !== null) {
      // Local Kokoro utterances run their own watchdogs (cold-synthesis
      // window, playback-duration watchdog). The browser no-start watchdog
      // must never kill a slow-but-healthy synthesis when new items arrive.
      if (this.activeIsLocal || this.status !== 'speaking' || !this.isWatchdogExpired()) return
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

    const { ttsProvider, localTTSAvailable } = useTTSStore.getState()
    this.activeIsLocal = ttsProvider === 'kokoro'
    if (ttsProvider === 'kokoro' && !capabilityChecked) {
      void this.waitForLocalTTS(item, utteranceId)
    } else if (ttsProvider === 'kokoro' && localTTSAvailable) {
      void this.speakLocal(item, utteranceId)
    } else if (ttsProvider === 'kokoro') {
      // A previous capability check cached an unavailable result, but the
      // engine may have become available since (model download completed,
      // server restart, etc.). Re-check once per process so a transient
      // startup issue does not permanently disable local neural TTS.
      capabilityChecked = false
      void this.waitForLocalTTS(item, utteranceId)
    } else {
      this.scheduleNoStartWatchdog(utteranceId)
      this.speakViaBrowser(item, utteranceId)
    }
  }

  private async waitForLocalTTS(
    item: { text: string; opts: EnqueueOptions },
    utteranceId: number,
  ) {
    await refreshLocalTTSCapability()
    if (!this.isActiveUtterance(utteranceId)) return
    if (useTTSStore.getState().localTTSAvailable) {
      void this.speakLocal(item, utteranceId)
      return
    }
    console.error('Kokoro TTS is selected but unavailable; no speech was produced.')
    this.finishCurrentUtterance(false)
    Promise.resolve().then(() => this.processNext())
  }

  /**
   * Use the selected local neural TTS engine without silently switching
   * providers. The user can select browser speech explicitly in Settings.
   */
  private async speakLocal(
    item: { text: string; opts: EnqueueOptions },
    utteranceId: number,
  ) {
    // Once the browser path has taken over (or the local attempt was
    // abandoned) any late fetch/audio result must be ignored to avoid
    // speaking twice or restarting an in-flight utterance.
    let localAbandoned = false
    // True when the LOCAL_START_WINDOW_MS watchdog aborted the request: that
    // is a real synthesis failure, unlike an intentional cancel below.
    let synthesisTimedOut = false
    let synthesisController: AbortController | null = null
    let synthesisTimeout: ReturnType<typeof setTimeout> | null = null
    // Mirrors the in-flight controller so the catch (outside the try scope)
    // can tell an intentional cancel from a real failure.
    let activeController: AbortController | null = null

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

    const stopWithoutFallback = () => {
      if (localAbandoned || !this.isActiveUtterance(utteranceId)) return
      localAbandoned = true
      this.clearLocalStartWatchdog(localStartWatchdog)
      clearSynthesisRequest()
      this.stopLocalAudio()
      this.localAudioElement = null
      this.clearNoStartWatchdog()
      console.error('Kokoro TTS could not synthesize the utterance.')
      this.finishCurrentUtterance(false)
      Promise.resolve().then(() => this.processNext())
    }

    const localStartWatchdog = setTimeout(() => {
      if (this.localStartWatchdog === localStartWatchdog) {
        this.localStartWatchdog = null
      }
      stopWithoutFallback()
    }, LOCAL_START_WINDOW_MS)
    this.localStartWatchdog = localStartWatchdog

    try {
      const lang = item.opts.lang || i18n.language || 'es'
      const baseLang = lang.split('-')[0]
      // The local engine uses its own voice selection (specific Kokoro voice
      // names); `selectedVoice` remains the browser voice used by
      // speakViaBrowser so the two paths never interfere.
      const { localVoice: voicePref, localSpeed } = useTTSStore.getState()
      const token = useAuthStore.getState().token || ''

      const controller = new AbortController()
      activeController = controller
      synthesisController = controller
      synthesisTimeout = setTimeout(() => {
        synthesisTimedOut = true
        controller.abort()
      }, LOCAL_START_WINDOW_MS)
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
          // The user's base speed (Settings) is scaled by the per-message
          // rate modifier and clamped to the range the backend accepts.
          speed: clampLocalSpeed(localSpeed * (item.opts.rate || 1.0)),
        }),
        signal: controller.signal,
      })
      // The headers have arrived, but the WAV body is still unread. Do not
      // abort the controller here: aborting it cancels res.blob() and turns a
      // successful 200 response into AbortError before playback can start.
      if (synthesisTimeout !== null) {
        clearTimeout(synthesisTimeout)
        synthesisTimeout = null
      }
      synthesisController = null
      if (this.localSynthesisCleanup === clearSynthesisRequest) {
        this.localSynthesisCleanup = null
      }
      if (localAbandoned) return
      if (!res.ok) {
        stopWithoutFallback()
        return
      }

      const blob = await res.blob()
      if (localAbandoned || !this.isActiveUtterance(utteranceId)) return

      const url = URL.createObjectURL(blob)
      const audio = this.localAudioElement ?? this.unlockedAudio ?? new window.Audio()
      if (this.unlockedAudio === audio) {
        audio.pause()
        this.unlockedAudio = null
      }
      this.localAudioElement = audio
      audio.muted = false
      audio.volume = 1
      audio.src = url
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
        // A successful synthesis can still fail at the device/playback layer
        // (missing output device, autoplay policy, invalid decoder, etc.).
        // Keep the selected provider explicit: stop and report the failure
        // instead of silently switching to browser speech.
        stopWithoutFallback()
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
    } catch (error) {
      this.clearLocalStartWatchdog(localStartWatchdog)
      clearSynthesisRequest()
      // Cancelling the previous utterance when a newer one is enqueued (or
      // the queue is cleared) rejects the in-flight request with AbortError;
      // that is intentional, not a failure. Report only real failures: the
      // start timeout, network errors, or playback errors.
      if (!localAbandoned && (!activeController?.signal.aborted || synthesisTimedOut)) {
        console.error('Kokoro TTS playback/synthesis error', error)
        stopWithoutFallback()
      }
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
    this.activeIsLocal = false
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

if (typeof document !== 'undefined') {
  const unlockAudio = () => tts.unlock()
  document.addEventListener('pointerdown', unlockAudio, { capture: true, passive: true })
  document.addEventListener('keydown', unlockAudio, { capture: true })
}
import { clampLocalSpeed, useTTSStore, type WarmupStatus } from '../store/ttsStore'
import { useAuthStore } from '../store/authStore'
import i18n from '../i18n/index'
import { config } from '../config'
