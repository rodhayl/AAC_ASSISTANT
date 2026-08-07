import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Learning } from '../src/pages/Learning'

const getApi = vi.hoisted(() => vi.fn())
const postApi = vi.hoisted(() => vi.fn())

const authStoreMock = vi.hoisted(() => {
  const user = {
    id: 1,
    username: 'admin1',
    user_type: 'admin',
    settings: { voice_mode_enabled: true },
  }
  const state = { user, token: 'test-token' };
  const hook = ((selector?: (value: typeof state) => unknown) =>
    selector ? selector(state) : state) as ((selector?: (value: typeof state) => unknown) => unknown) & {
    getState: () => {
      user: typeof user
      token: string
      logout: () => void
    }
  }
  hook.getState = () => ({ user, token: 'test-token', logout: () => {} })
  return hook
})

vi.mock('../src/lib/api', () => ({
  default: { get: getApi, post: postApi },
}))

vi.mock('../src/store/authStore', () => ({ useAuthStore: authStoreMock }))

// The real learningStore is used on purpose: its startSession action performs
// the POST to /learning/start, so asserting on postApi proves the selected
// mode key actually leaves the page and reaches the backend payload.
vi.mock('../src/store/boardStore', () => {
  const state = { fetchBoards: vi.fn() };
  const useBoardStore = (selector?: (value: typeof state) => unknown) =>
    selector ? selector(state) : state;
  return { useBoardStore };
})

vi.mock('../src/store/toastStore', () => {
  const state = { addToast: vi.fn() };
  const useToastStore = (selector?: (value: typeof state) => unknown) =>
    selector ? selector(state) : state;
  return { useToastStore };
})

// The page only enqueues speech for assistant messages; keep the TTS module
// out of this test so the real i18n/speechSynthesis chain is not required.
vi.mock('../src/lib/tts', () => ({
  tts: { enqueue: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string | { defaultValue?: string }, options?: Record<string, string>) => {
      if (typeof defaultValue === 'string') {
        let text = defaultValue
        for (const [name, value] of Object.entries(options || {})) {
          text = text.replace(`{{${name}}}`, value)
        }
        return text
      }
      return defaultValue?.defaultValue ?? key
    },
    i18n: { language: 'en' },
  }),
}))

vi.mock('../src/components/learning/LearningChatPanel', () => ({
  LearningChatPanel: ({ onStartSession }: { onStartSession: () => void }) => (
    <button data-testid="start-session" onClick={() => onStartSession()}>
      Start
    </button>
  ),
}))

vi.mock('../src/components/learning/LearningHistoryPanel', () => ({
  LearningHistoryPanel: () => null,
}))

vi.mock('../src/components/learning/LearningSymbolPanel', () => ({
  LearningSymbolPanel: () => null,
}))

vi.mock('../src/components/learning/BoardsAndTopicsSidebar', () => ({
  BoardsAndTopicsSidebar: () => null,
}))

vi.mock('../src/components/learning/useVoiceRecorder', () => ({
  useVoiceRecorder: () => ({
    isRecording: false,
    hasRecording: false,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    discardRecording: vi.fn(),
    sendRecording: vi.fn(),
  }),
}))

const modes = [
  { id: 1, name: 'Practice', key: 'practice', description: 'Default practice mode' },
  { id: 2, name: 'Andaluz', key: 'andalusian', description: 'Speaks Andalusian Spanish' },
]

// The mock store exposes the new difficulty controls as no-op state actions;
// this test focuses on mode_key payloads.


describe('Learning mode dropdown', () => {
  beforeEach(() => {
    getApi.mockReset()
    postApi.mockReset()
    getApi.mockImplementation((url: string) => {
      if (url.includes('/learning-modes/')) {
        return Promise.resolve({ data: modes })
      }
      return Promise.resolve({ data: { sessions: [] } })
    })
    postApi.mockResolvedValue({
      data: { success: true, session_id: 99, welcome_message: 'Welcome' },
    })
    localStorage.clear()
  })

  it('sends the mode key selected in the dropdown to the session start endpoint', async () => {
    render(<Learning />)

    const select = await screen.findByRole('combobox', { name: 'Mode:' })
    await screen.findByRole('option', { name: 'Andaluz' })
    fireEvent.change(select, { target: { value: 'andalusian' } })

    fireEvent.click(screen.getByTestId('start-session'))

    await waitFor(() => {
      expect(postApi).toHaveBeenCalledWith(
        '/learning/start',
        expect.objectContaining({ mode_key: 'andalusian' }),
        expect.anything(),
      )
    })
  })

  it('sends the default mode key when the dropdown is untouched', async () => {
    render(<Learning />)

    await screen.findByRole('combobox', { name: 'Mode:' })
    fireEvent.click(screen.getByTestId('start-session'))

    await waitFor(() => {
      expect(postApi).toHaveBeenCalledWith(
        '/learning/start',
        expect.objectContaining({ mode_key: 'practice' }),
        expect.anything(),
      )
    })
  })

  it('includes the topic/purpose alongside the mode key in the payload', async () => {
    render(<Learning />)

    await screen.findByRole('combobox', { name: 'Mode:' })
    fireEvent.click(screen.getByTestId('start-session'))

    await waitFor(() => {
      expect(postApi).toHaveBeenCalledWith(
        '/learning/start',
        expect.objectContaining({
          mode_key: 'practice',
          topic: 'general conversation',
          purpose: 'practice',
        }),
        expect.anything(),
      )
    })
  })

  it('sends a fixed difficulty selected in the header when starting a session', async () => {
    render(<Learning />)

    await screen.findByRole('combobox', { name: 'Difficulty:' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Difficulty:' }), {
      target: { value: 'advanced' },
    })
    fireEvent.click(screen.getByTestId('start-session'))

    await waitFor(() => {
      expect(postApi).toHaveBeenCalledWith(
        '/learning/start',
        expect.objectContaining({ difficulty: 'advanced' }),
        expect.anything(),
      )
    })
  })
})
