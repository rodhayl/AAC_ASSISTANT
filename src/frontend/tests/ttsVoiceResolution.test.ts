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

describe('browser voiceURI resolution', () => {
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

  it('selects the exact stored browser voiceURI even when it exceeds 20 chars', async () => {
    const longUri = 'Microsoft Sabina - Spanish (Mexico)'
    expect(longUri.length).toBeGreaterThan(20)
    const voices = [
      { name: 'Microsoft Sabina - Spanish (Mexico)', lang: 'es-MX', voiceURI: longUri },
      { name: 'Google US English', lang: 'en-US', voiceURI: 'Google US English' },
    ]
    speechSynthesis.getVoices.mockReturnValue(voices)

    const { tts } = await import('../src/lib/tts')
    const { useTTSStore } = await import('../src/store/ttsStore')
    await selectBrowserTTS()
    useTTSStore.getState().setSelectedVoice(longUri)

    tts.enqueue('Hola', { key: 'long-voice-uri' })

    expect(utterances[0].voice).not.toBeNull()
    expect(utterances[0].voice?.voiceURI).toBe(longUri)
  })

  it('falls back to a locale voice when the stored URI is absent on this device', async () => {
    // The stored preference came from another device; this browser only has
    // English voices. pickBestVoice must resolve a same-locale voice instead
    // of crashing or leaving the utterance without any voice.
    const voices = [{ name: 'Google US English', lang: 'en-US', voiceURI: 'Google US English' }]
    speechSynthesis.getVoices.mockReturnValue(voices)

    const i18n = (await import('../src/i18n/index')).default
    await i18n.changeLanguage('en-US')

    const { tts } = await import('../src/lib/tts')
    const { useTTSStore } = await import('../src/store/ttsStore')
    await selectBrowserTTS()
    useTTSStore.getState().setSelectedVoice('urn:no-such-voice-on-this-device')

    tts.enqueue('Hello', { key: 'voice-fallback' })

    expect(utterances).toHaveLength(1)
    expect(utterances[0].voice).not.toBeNull()
    expect(utterances[0].voice?.voiceURI).toBe('Google US English')
  })
})
