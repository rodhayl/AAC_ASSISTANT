type Status = 'idle' | 'speaking'

interface EnqueueOptions {
  key?: string | number
  rate?: number
  pitch?: number
  lang?: string
}

class TTSQueue {
  private queue: Array<{ text: string; opts: EnqueueOptions }>
  private status: Status
  private listeners: Array<(s: Status) => void>
  private lastSpokenAt: Map<string | number, number>
  private debounceMs: number

  constructor() {
    this.queue = []
    this.status = 'idle'
    this.listeners = []
    this.lastSpokenAt = new Map()
    this.debounceMs = 250
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
    if (this.status === 'idle') {
      this.processNext()
    }
  }

  private processNext() {
    if (this.queue.length === 0) {
      this.setStatus('idle')
      return
    }
    const item = this.queue.shift()!
    if (!('speechSynthesis' in window)) {
      this.setStatus('idle')
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
        const voices = window.speechSynthesis.getVoices()
        let chosen: SpeechSynthesisVoice | null = null
        
        // 1. Try to find by exact voiceURI or name
        chosen = voices.find(v => v.voiceURI === pref || v.name === pref) || null

        if (!chosen) {
          const currentLocale = i18n.language || 'es'
          const isSpanish = /^(es)(-|$)/i.test(currentLocale)
          const langPrefer = isSpanish ? /es/i : /en/i
          
          if (pref === 'female') {
            chosen = voices.find(v => /female/i.test(v.name) && langPrefer.test(v.lang))
              || voices.find(v => langPrefer.test(v.lang))
              || null
          } else if (pref === 'male') {
            chosen = voices.find(v => /male/i.test(v.name) && langPrefer.test(v.lang))
              || voices.find(v => langPrefer.test(v.lang))
              || null
          } else {
            // default or unknown
            chosen = voices.find(v => langPrefer.test(v.lang)) || null
          }
        }
        
        // Force language if we are in Spanish mode and no voice was explicitly chosen that contradicts it
        // Actually, if a user picked a specific voice, we should probably trust it matches their intent.
        // But if we fell back to 'female'/'male', we should ensure language matches.
        // The previous logic forced 'es-ES' if isSpanish was true. We should keep that for safety
        // unless the chosen voice is explicitly from another language (which shouldn't happen if filtered correctly).
        
        const currentLocale = i18n.language || 'es'
        const isSpanish = /^(es)(-|$)/i.test(currentLocale)
        if (isSpanish && !chosen) u.lang = 'es-ES'
        
        if (chosen) {
            u.voice = chosen
            u.lang = chosen.lang // Use the voice's language
        } else if (isSpanish) {
             u.lang = 'es-ES'
        }

      } catch { /* voice selection not critical */ }

      u.onstart = () => this.setStatus('speaking')
      u.onend = () => {
        this.setStatus('idle')
        // Continue with next queued item
        // Use microtask to avoid re-entrancy issues
        Promise.resolve().then(() => this.processNext())
      }
      u.onerror = () => {
        this.setStatus('idle')
        Promise.resolve().then(() => this.processNext())
      }
      window.speechSynthesis.speak(u)
    } catch {
      this.setStatus('idle')
    }
  }
}

export const tts = new TTSQueue()
import { useTTSStore } from '../store/ttsStore'
import i18n from '../i18n/index'
