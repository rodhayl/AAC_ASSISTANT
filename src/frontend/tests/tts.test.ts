type FakeUtterance = {
  text: string
  rate: number
  pitch: number
  lang: string
  voice: SpeechSynthesisVoice | null
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
}

describe('tts queue watchdog', () => {
  let speechSynthesis: {
    speak: ReturnType<typeof vi.fn>
    cancel: ReturnType<typeof vi.fn>
    getVoices: ReturnType<typeof vi.fn>
  }
  let utterances: FakeUtterance[]
  let originalSpeechSynthesis: PropertyDescriptor | undefined

  beforeEach(() => {
    vi.useFakeTimers()
    vi.resetModules()
    utterances = []
    speechSynthesis = {
      speak: vi.fn((utterance: FakeUtterance) => {
        utterances.push(utterance)
      }),
      cancel: vi.fn(),
      getVoices: vi.fn(() => []),
    }
    originalSpeechSynthesis = Object.getOwnPropertyDescriptor(window, 'speechSynthesis')
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: speechSynthesis,
    })

    class TestSpeechSynthesisUtterance {
      text: string
      rate = 1
      pitch = 1
      lang = ''
      voice: SpeechSynthesisVoice | null = null
      onstart: (() => void) | null = null
      onend: (() => void) | null = null
      onerror: (() => void) | null = null

      constructor(text: string) {
        this.text = text
      }
    }
    vi.stubGlobal('SpeechSynthesisUtterance', TestSpeechSynthesisUtterance)
  })

  afterEach(() => {
    if (originalSpeechSynthesis) {
      Object.defineProperty(window, 'speechSynthesis', originalSpeechSynthesis)
    } else {
      delete (window as Window & { speechSynthesis?: unknown }).speechSynthesis
    }
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  async function selectBrowserTTS() {
    const { useTTSStore } = await import('../src/store/ttsStore')
    useTTSStore.getState().setTTSProvider('browser')
  }

  it('advances a queue when speech events never fire', async () => {
    const { tts } = await import('../src/lib/tts')
    await selectBrowserTTS()

    tts.enqueue('A', { key: 'a' })
    tts.enqueue('B', { key: 'b' })

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(1)
    expect(utterances[0].text).toBe('A')
    expect(tts.getStatus()).toBe('speaking')

    await vi.advanceTimersByTimeAsync(1_500)

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(2)
    expect(utterances[1].text).toBe('B')
  })

  it('marks speech as active optimistically and recovers when events never fire', async () => {
    const { tts } = await import('../src/lib/tts')
    await selectBrowserTTS()

    tts.enqueue('A', { key: 'eventless-a' })

    expect(tts.getStatus()).toBe('speaking')

    await vi.advanceTimersByTimeAsync(1_500)

    expect(tts.getStatus()).toBe('idle')
  })

  it('returns to idle when an event-firing utterance ends', async () => {
    speechSynthesis.speak.mockImplementation((utterance: FakeUtterance) => {
      utterances.push(utterance)
      utterance.onstart?.()
    })
    const { tts } = await import('../src/lib/tts')
    await selectBrowserTTS()

    tts.enqueue('A', { key: 'eventful-a' })

    expect(tts.getStatus()).toBe('speaking')
    utterances[0].onend?.()
    await Promise.resolve()

    expect(tts.getStatus()).toBe('idle')
  })

  it('does not cancel healthy speech before its end event', async () => {
    speechSynthesis.speak.mockImplementation((utterance: FakeUtterance) => {
      utterances.push(utterance)
      utterance.onstart?.()
    })
    const { tts } = await import('../src/lib/tts')
    await selectBrowserTTS()
    const cancelCountBeforeEnqueue = speechSynthesis.cancel.mock.calls.length

    tts.enqueue('A', { key: 'normal-a' })
    tts.enqueue('B', { key: 'normal-b' })

    await vi.advanceTimersByTimeAsync(2_000)

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(1)
    expect(speechSynthesis.cancel).toHaveBeenCalledTimes(cancelCountBeforeEnqueue + 1)

    utterances[0].onend?.()
    await Promise.resolve()

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(2)
    expect(utterances[1].text).toBe('B')
  })

  it('recovers when speech starts but never ends', async () => {
    speechSynthesis.speak.mockImplementation((utterance: FakeUtterance) => {
      utterances.push(utterance)
      utterance.onstart?.()
    })
    const { tts } = await import('../src/lib/tts')
    await selectBrowserTTS()

    tts.enqueue('A', { key: 'started-a' })
    tts.enqueue('B', { key: 'started-b' })

    await vi.advanceTimersByTimeAsync(14_999)
    expect(speechSynthesis.speak).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1)

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(2)
    expect(utterances[1].text).toBe('B')
  })
})

// ---------------------------------------------------------------------------
// Local neural TTS path (backend Kokoro synthesis without implicit fallback)
// ---------------------------------------------------------------------------
// LOCAL_START_WINDOW_MS in ../src/lib/tts is 12_000; the race-guard test
// relies on the watchdog stopping the utterance after that window.
const LOCAL_START_WINDOW_MS = 12_000

describe('tts queue local neural path', () => {
  let speechSynthesis: {
    speak: ReturnType<typeof vi.fn>
    cancel: ReturnType<typeof vi.fn>
    getVoices: ReturnType<typeof vi.fn>
  }
  let utterances: FakeUtterance[]
  let audioInstances: Array<{
    play: ReturnType<typeof vi.fn>
    pause: ReturnType<typeof vi.fn>
    onended: (() => void) | null
    onerror: (() => void) | null
    duration: number
    src: string
  }>
  let fetchMock: ReturnType<typeof vi.fn>
  let originalSpeechSynthesis: PropertyDescriptor | undefined
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL

  beforeEach(() => {
    vi.useFakeTimers()
    vi.resetModules()
    utterances = []
    audioInstances = []
    speechSynthesis = {
      speak: vi.fn((utterance: FakeUtterance) => {
        utterances.push(utterance)
      }),
      cancel: vi.fn(),
      getVoices: vi.fn(() => []),
    }
    originalSpeechSynthesis = Object.getOwnPropertyDescriptor(window, 'speechSynthesis')
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: speechSynthesis,
    })

    class TestSpeechSynthesisUtterance {
      text: string
      rate = 1
      pitch = 1
      lang = ''
      voice: SpeechSynthesisVoice | null = null
      onstart: (() => void) | null = null
      onend: (() => void) | null = null
      onerror: (() => void) | null = null

      constructor(text: string) {
        this.text = text
      }
    }
    vi.stubGlobal('SpeechSynthesisUtterance', TestSpeechSynthesisUtterance)

    class TestAudio {
      onended: (() => void) | null = null
      onerror: (() => void) | null = null
      duration = 2
      src = ''
      play: ReturnType<typeof vi.fn>
      pause: ReturnType<typeof vi.fn>

      constructor(url: string) {
        this.src = url
        this.play = vi.fn(async () => {})
        this.pause = vi.fn()
        audioInstances.push(this)
      }
    }
    vi.stubGlobal('Audio', TestAudio)

    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    URL.createObjectURL = vi.fn(() => 'blob:fake')
    URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    if (originalSpeechSynthesis) {
      Object.defineProperty(window, 'speechSynthesis', originalSpeechSynthesis)
    } else {
      delete (window as Window & { speechSynthesis?: unknown }).speechSynthesis
    }
    URL.createObjectURL = originalCreateObjectURL
    URL.revokeObjectURL = originalRevokeObjectURL
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  const flush = async () => {
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(0)
  }

  async function loadLocalTTS() {
    const { tts } = await import('../src/lib/tts')
    const { useTTSStore } = await import('../src/store/ttsStore')
    useTTSStore.getState().setTTSProvider('kokoro')
    useTTSStore.getState().setLocalTTSAvailable(true)
    return tts
  }

  it('synthesizes with the local engine when enabled and never touches browser speech', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/providers/voice-status')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ tts_local: { available: true } }),
        })
      }
      return Promise.resolve({
        ok: true,
        blob: async () => new Blob(['fake-wav']),
      })
    })
    const tts = await loadLocalTTS()

    tts.enqueue('Hola, ¿cómo estás?', { key: 'local-ok', lang: 'es' })
    await flush()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/providers/tts/synthesize'),
      expect.objectContaining({ method: 'POST' }),
    )
    const calls = fetchMock.mock.calls as Array<[unknown, { body: string }]>
    const synthesisCall = calls.find((call) => call[1]?.body)
    expect(synthesisCall).toBeDefined()
    expect(JSON.parse(synthesisCall![1].body)).toMatchObject({
      text: 'Hola, ¿cómo estás?',
      lang: 'es',
      voice: 'default',
    })
    expect(audioInstances).toHaveLength(1)
    expect(audioInstances[0].play).toHaveBeenCalled()
    expect(tts.getStatus()).toBe('speaking')
    expect(speechSynthesis.speak).not.toHaveBeenCalled()

    tts.cancelAll()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake')
    expect(tts.getStatus()).toBe('idle')

    audioInstances[0].onended?.()
    await flush()
    expect(tts.getStatus()).toBe('idle')
  })

  it('does not abort a successful WAV response before reading its body', async () => {
    let synthesisSignal: AbortSignal | undefined
    let blobRead = false
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/providers/voice-status')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ tts_local: { available: true } }),
        })
      }
      synthesisSignal = init?.signal
      return Promise.resolve({
        ok: true,
        blob: async () => {
          blobRead = true
          expect(synthesisSignal?.aborted).toBe(false)
          return new Blob(['fake-wav'])
        },
      })
    })
    const tts = await loadLocalTTS()

    tts.enqueue('Respuesta local', { key: 'local-body', lang: 'es' })
    await flush()

    expect(blobRead).toBe(true)
    expect(audioInstances[0].play).toHaveBeenCalled()
  })

  it('does not switch to browser speech when Kokoro answers with an error', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.includes('/providers/voice-status')
        ? Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: true } }) })
        : Promise.resolve({ ok: false }),
    )
    const tts = await loadLocalTTS()

    tts.enqueue('Hola', { key: 'local-not-ok', lang: 'es' })
    await flush()

    expect(speechSynthesis.speak).not.toHaveBeenCalled()
    expect(audioInstances).toHaveLength(0)
  })

  it('does not switch to browser speech when the Kokoro request fails', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.includes('/providers/voice-status')
        ? Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: true } }) })
        : Promise.reject(new Error('network down')),
    )
    const tts = await loadLocalTTS()

    tts.enqueue('Adiós', { key: 'local-reject', lang: 'es' })
    await flush()

    expect(speechSynthesis.speak).not.toHaveBeenCalled()
  })

  it('does not switch to browser speech when synthesized audio cannot play', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.includes('/providers/voice-status')
        ? Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: true } }) })
        : Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) }),
    )
    const tts = await loadLocalTTS()

    tts.enqueue('Salida de audio', { key: 'local-playback-error', lang: 'es' })
    await flush()
    expect(audioInstances).toHaveLength(1)
    expect(speechSynthesis.speak).not.toHaveBeenCalled()

    audioInstances[0].onerror?.()
    await flush()

    expect(speechSynthesis.speak).not.toHaveBeenCalled()
    expect(tts.getStatus()).toBe('idle')
  })

  it('does not speak when Kokoro is selected but unavailable on the backend', async () => {
    const { tts } = await import('../src/lib/tts')
    const { useTTSStore } = await import('../src/store/ttsStore')
    useTTSStore.getState().setTTSProvider('kokoro')
    // localTTSAvailable stays false: the queue must not even try to fetch.
    useTTSStore.getState().setLocalTTSAvailable(false)

    tts.enqueue('Hola', { key: 'local-unavailable', lang: 'es' })
    await flush()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/providers/voice-status'),
      expect.anything(),
    )
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(speechSynthesis.speak).not.toHaveBeenCalled()
    expect(audioInstances).toHaveLength(0)
  })

  it('does not speak when a late local response arrives after Kokoro timeout', async () => {
    let resolveFetch: (value: unknown) => void = () => {}
    const deferred = new Promise((resolve) => {
      resolveFetch = resolve
    })
    fetchMock.mockImplementation(() => deferred)
    const tts = await loadLocalTTS()

    tts.enqueue('Hola', { key: 'local-race', lang: 'es' })

    // The synthesize request never answers: the start watchdog must stop
    // the utterance after the local start window.
    await vi.advanceTimersByTimeAsync(LOCAL_START_WINDOW_MS)
    expect(speechSynthesis.speak).not.toHaveBeenCalled()
    expect(audioInstances).toHaveLength(0)

    // A late response arrives after the utterance already stopped; it must be
    // ignored so the text is not spoken twice.
    resolveFetch({ ok: true, blob: async () => new Blob(['fake-wav']) })
    await flush()

    expect(audioInstances).toHaveLength(0)
    expect(speechSynthesis.speak).not.toHaveBeenCalled()
    expect(tts.getStatus()).toBe('idle')
  })

  it('does not log an error when a pending synthesis is cancelled by a newer utterance', async () => {
    // A fetch that never resolves: the synthesis stays in flight while the
    // next utterance (or cancelAll) aborts it.
    const deferred = new Promise(() => {})
    fetchMock.mockImplementation(() => deferred)
    const tts = await loadLocalTTS()
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    tts.enqueue('Hola', { key: 'local-cancel-1', lang: 'es' })
    await flush()

    // Replacing the utterance cancels the in-flight synthesis request; the
    // AbortError is intentional and must not be reported as a failure.
    tts.cancelAll()
    await flush()

    expect(errorSpy).not.toHaveBeenCalledWith(
      'Kokoro TTS playback/synthesis error',
      expect.anything(),
    )
    errorSpy.mockRestore()
  })
})
