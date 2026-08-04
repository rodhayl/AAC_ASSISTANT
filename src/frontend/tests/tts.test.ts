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

  it('advances a queue when speech events never fire', async () => {
    const { tts } = await import('../src/lib/tts')

    tts.enqueue('A', { key: 'a' })
    tts.enqueue('B', { key: 'b' })

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(1)
    expect(utterances[0].text).toBe('A')

    await vi.advanceTimersByTimeAsync(1_500)

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(2)
    expect(utterances[1].text).toBe('B')
  })

  it('does not cancel healthy speech before its end event', async () => {
    speechSynthesis.speak.mockImplementation((utterance: FakeUtterance) => {
      utterances.push(utterance)
      utterance.onstart?.()
    })
    const { tts } = await import('../src/lib/tts')
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

    tts.enqueue('A', { key: 'started-a' })
    tts.enqueue('B', { key: 'started-b' })

    await vi.advanceTimersByTimeAsync(14_999)
    expect(speechSynthesis.speak).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1)

    expect(speechSynthesis.speak).toHaveBeenCalledTimes(2)
    expect(utterances[1].text).toBe('B')
  })
})
