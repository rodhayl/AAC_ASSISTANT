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
// LOCAL_START_WINDOW_MS in ../src/lib/tts is 60_000; the race-guard test
// relies on the watchdog stopping the utterance after that window.
const LOCAL_START_WINDOW_MS = 60_000

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
  let originalWindowAudio: typeof Audio
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
    originalWindowAudio = window.Audio
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
    Object.defineProperty(window, 'Audio', {
      configurable: true,
      value: TestAudio,
    })

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
    Object.defineProperty(window, 'Audio', {
      configurable: true,
      value: originalWindowAudio,
    })
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

  it('applies the configured Kokoro speed to synthesis requests', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.includes('/providers/voice-status')
        ? Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: true } }) })
        : Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) }),
    )
    const tts = await loadLocalTTS()
    const { useTTSStore } = await import('../src/store/ttsStore')
    useTTSStore.getState().setLocalSpeed(1.5)

    tts.enqueue('Más rápido', { key: 'local-speed', lang: 'es' })
    await flush()

    const synthesisBodies = () =>
      (fetchMock.mock.calls as Array<[unknown, { body: string }]>)
        .filter((call) => call[1]?.body)
        .map((call) => JSON.parse(call[1].body) as { speed: number })
    expect(synthesisBodies()[0].speed).toBe(1.5)

    // Per-message rate modifiers multiply the base speed, clamped to the
    // range the Kokoro endpoint accepts.
    audioInstances[0].onended?.()
    await flush()
    tts.enqueue('Demasiado rápido', { key: 'local-speed-clamped', lang: 'es', rate: 2 })
    await flush()
    expect(synthesisBodies().at(-1)!.speed).toBe(2.0)

    useTTSStore.getState().setLocalSpeed(1.0)
    localStorage.removeItem('aac_local_speed')
  })

  it('reuses audio unlocked by a user gesture for synthesized playback', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.includes('/providers/voice-status')
        ? Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: true } }) })
        : Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) }),
    )
    const tts = await loadLocalTTS()

    tts.unlock()
    expect(audioInstances).toHaveLength(1)
    tts.enqueue('Respuesta después de un clic', { key: 'local-unlocked', lang: 'es' })
    await flush()

    expect(audioInstances).toHaveLength(1)
    expect(audioInstances[0].play).toHaveBeenCalledTimes(2)
    expect(audioInstances[0].src).toBe('blob:fake')
    expect(speechSynthesis.speak).not.toHaveBeenCalled()

    audioInstances[0].onended?.()
    await flush()
    tts.enqueue('La siguiente respuesta', { key: 'local-unlocked-next', lang: 'es' })
    await flush()

    expect(audioInstances).toHaveLength(1)
    expect(audioInstances[0].play).toHaveBeenCalledTimes(3)
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

  it('keeps the first queued response pending during a cold synthesis', async () => {
    let resolveFirstSynthesis: ((value: unknown) => void) | undefined
    let synthesisCount = 0
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/providers/voice-status')) {
        return Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: true } }) })
      }
      synthesisCount += 1
      if (synthesisCount === 1) {
        return new Promise((resolve) => {
          resolveFirstSynthesis = resolve
        })
      }
      return Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) })
    })
    const tts = await loadLocalTTS()

    tts.enqueue('La primera respuesta', { key: 'local-cold-first', lang: 'es' })
    tts.enqueue('La segunda respuesta', { key: 'local-cold-second', lang: 'es' })
    await flush()

    await vi.advanceTimersByTimeAsync(15_000)
    expect(synthesisCount).toBe(1)

    resolveFirstSynthesis?.({ ok: true, blob: async () => new Blob(['fake-wav']) })
    await flush()
    expect(audioInstances).toHaveLength(1)

    audioInstances[0].onended?.()
    await flush()
    expect(synthesisCount).toBe(2)
  })

  it('does not kill an in-flight local synthesis when a message is enqueued after the no-start window', async () => {
    // Real Kokoro synthesis routinely takes longer than the 1.5s browser
    // no-start watchdog. A message enqueued while synthesis is still running
    // must wait in the queue, not destroy the active utterance.
    let resolveFirstSynthesis: ((value: unknown) => void) | undefined
    let synthesisCount = 0
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/providers/voice-status')) {
        return Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: true } }) })
      }
      synthesisCount += 1
      if (synthesisCount === 1) {
        return new Promise((resolve) => {
          resolveFirstSynthesis = resolve
        })
      }
      return Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) })
    })
    const tts = await loadLocalTTS()

    tts.enqueue('La primera respuesta', { key: 'local-slow-first', lang: 'es' })
    await flush()

    // The next message arrives seconds later, while the first synthesis is
    // still in flight (e.g. the user answers before the question audio has
    // finished synthesizing).
    await vi.advanceTimersByTimeAsync(2_000)
    tts.enqueue('La segunda respuesta', { key: 'local-slow-second', lang: 'es' })
    await flush()
    expect(synthesisCount).toBe(1)

    resolveFirstSynthesis?.({ ok: true, blob: async () => new Blob(['fake-wav']) })
    await flush()
    expect(audioInstances).toHaveLength(1)
    expect(audioInstances[0].play).toHaveBeenCalledTimes(1)
    expect(tts.getStatus()).toBe('speaking')

    audioInstances[0].onended?.()
    await flush()
    expect(synthesisCount).toBe(2)
    expect(audioInstances[0].play).toHaveBeenCalledTimes(2)
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

  it('warmup pre-checks capability and pre-loads both models in one batch request', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/providers/voice-status')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ tts_local: { available: true } }),
        })
      }
      if (url.includes('/providers/warmup')) {
        const body = JSON.parse(String(init?.body)) as { targets: string[] }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            tts: { warmed: body.targets.includes('tts') },
            speech: { warmed: body.targets.includes('speech') },
            vector: { warmed: body.targets.includes('vector') },
          }),
        })
      }
      return Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) })
    })
    const { tts, warmup } = await import('../src/lib/tts')
    const { useTTSStore } = await import('../src/store/ttsStore')
    useTTSStore.getState().setTTSProvider('kokoro')

    warmup()
    await flush()
    await flush()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/providers/voice-status'),
      expect.anything(),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/providers/warmup'),
      expect.objectContaining({ method: 'POST' }),
    )
    // All lazy models pre-load in a single batched request.
    const warmupCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/providers/warmup'),
    )
    const body = JSON.parse(String(warmupCall?.[1]?.body)) as { targets: string[] }
    expect(body.targets).toEqual(['tts', 'speech', 'vector'])

    // All three report ready for the settings indicators.
    expect(useTTSStore.getState().ttsWarmupStatus).toBe('ready')
    expect(useTTSStore.getState().speechWarmupStatus).toBe('ready')
    expect(useTTSStore.getState().vectorWarmupStatus).toBe('ready')

    // The warm-up is fire-and-forget: repeating it does not fire again.
    warmup()
    await flush()
    const warmups = fetchMock.mock.calls.filter(
      (call) => String(call[0]).includes('/providers/warmup'),
    )
    expect(warmups).toHaveLength(1)

    // The capability is now cached: the first enqueue skips the voice-status
    // round-trip and synthesizes directly.
    tts.enqueue('Hola', { key: 'local-warmup', lang: 'es' })
    await flush()
    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls.filter((url) => url.includes('/providers/voice-status'))).toHaveLength(1)
    expect(urls.filter((url) => url.includes('/providers/tts/synthesize'))).toHaveLength(1)
    expect(speechSynthesis.speak).not.toHaveBeenCalled()
  })

  it('warmup with the browser TTS provider skips the Kokoro target', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/providers/warmup')) {
        const body = JSON.parse(String(init?.body)) as { targets: string[] }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            speech: { warmed: body.targets.includes('speech') },
            vector: { warmed: body.targets.includes('vector') },
          }),
        })
      }
      return Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) })
    })
    const { warmup } = await import('../src/lib/tts')
    const { useTTSStore } = await import('../src/store/ttsStore')
    useTTSStore.getState().setTTSProvider('browser')

    warmup()
    await flush()
    await flush()

    // No Kokoro load for a browser-only speech user (and no capability
    // round-trip either), but the microphone and semantic search models are
    // still pre-loaded.
    const warmupCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/providers/warmup'),
    )
    const body = JSON.parse(String(warmupCall?.[1]?.body)) as { targets: string[] }
    expect(body.targets).toEqual(['speech', 'vector'])
    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls.filter((url) => url.includes('/providers/voice-status'))).toHaveLength(0)
    expect(useTTSStore.getState().ttsWarmupStatus).toBe('idle')
    expect(useTTSStore.getState().speechWarmupStatus).toBe('ready')
    expect(useTTSStore.getState().vectorWarmupStatus).toBe('ready')
  })

  it('warmup still pre-loads speech and vector when the local TTS engine is unavailable', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/providers/voice-status')) {
        return Promise.resolve({ ok: true, json: async () => ({ tts_local: { available: false } }) })
      }
      if (url.includes('/providers/warmup')) {
        const body = JSON.parse(String(init?.body)) as { targets: string[] }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            speech: { warmed: body.targets.includes('speech') },
            vector: { warmed: body.targets.includes('vector') },
          }),
        })
      }
      return Promise.resolve({ ok: true, blob: async () => new Blob(['fake-wav']) })
    })
    const { warmup } = await import('../src/lib/tts')
    const { useTTSStore } = await import('../src/store/ttsStore')
    useTTSStore.getState().setTTSProvider('kokoro')

    warmup()
    await flush()
    await flush()

    // The TTS target is dropped (engine unavailable) but the batched request
    // still fires for the other lazy models.
    const warmupCall = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/providers/warmup'),
    )
    const body = JSON.parse(String(warmupCall?.[1]?.body)) as { targets: string[] }
    expect(body.targets).toEqual(['speech', 'vector'])
    expect(useTTSStore.getState().ttsWarmupStatus).toBe('unavailable')
    expect(useTTSStore.getState().speechWarmupStatus).toBe('ready')
    expect(useTTSStore.getState().vectorWarmupStatus).toBe('ready')
  })
})
