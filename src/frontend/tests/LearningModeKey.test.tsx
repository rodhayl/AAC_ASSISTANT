import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Learning } from '../src/pages/Learning'

const getApi = vi.hoisted(() => vi.fn())
const postApi = vi.hoisted(() => vi.fn())

const authStoreMock = vi.hoisted(() => {
  const user = {
    id: 1,
    username: 'admin1',
    user_type: 'admin',
    settings: {
      voice_mode_enabled: true,
      default_learning_mode: undefined as string | undefined,
    },
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
  return { hook, user }
})

vi.mock('../src/lib/api', () => ({
  default: { get: getApi, post: postApi },
}))

vi.mock('../src/store/authStore', () => ({ useAuthStore: authStoreMock.hook }))

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
  tts: { enqueue: vi.fn(), cancelAll: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, string>) => {
      const options = typeof arg2 === 'object' ? arg2 : arg3;
      const defaults: Record<string, string> = {
        modeLabel: 'Mode',
        difficultyLabel: 'Difficulty',
        difficultyHelp: 'Difficulty selection',
        'difficulty.adaptive': 'Adaptive',
        'difficulty.basic': 'Basic',
        'difficulty.intermediate': 'Intermediate',
        'difficulty.advanced': 'Advanced',
      };
      let text = typeof arg2 === 'string' ? arg2 : defaults[key] ?? key;
      for (const [name, value] of Object.entries(options || {})) {
        text = text.replace(`{{${name}}}`, String(value));
      }
      return text;
    },
    i18n: { language: 'en' },
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
}));

// The chat panel renders the real TopicPicker in its empty state; clicking a
// topic card is the page's start-session affordance now.
vi.mock('../src/components/learning/LearningChatPanel', () => ({
  LearningChatPanel: ({ topicPicker }: { topicPicker: React.ReactNode }) => (
    <div data-testid="chat-panel">{topicPicker}</div>
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
    authStoreMock.user.settings.default_learning_mode = undefined
  })

  it('uses the persisted default mode in the dropdown and session payload', async () => {
    authStoreMock.user.settings.default_learning_mode = 'andalusian'
    render(<Learning />)

    const select = await screen.findByRole('combobox', { name: 'Mode:' })
    expect(select).toHaveValue('andalusian')
    fireEvent.click(screen.getByTestId('topic-card-general'))

    await waitFor(() => {
      expect(postApi).toHaveBeenCalledWith(
        '/learning/start',
        expect.objectContaining({ mode_key: 'andalusian' }),
        expect.anything(),
      )
    })
  })

  it('refreshes the mode catalog and default after a mode-change event', async () => {
    const refreshedMode = {
      id: 3,
      name: 'Roleplay',
      key: 'roleplay',
      description: 'Scenario practice',
    }
    let modeFetches = 0
    getApi.mockImplementation((url: string) => {
      if (url.includes('/learning-modes/')) {
        modeFetches += 1
        return Promise.resolve({ data: modeFetches === 1 ? modes : [...modes, refreshedMode] })
      }
      return Promise.resolve({ data: { sessions: [] } })
    })

    render(<Learning />)
    const select = await screen.findByRole('combobox', { name: 'Mode:' })

    act(() => {
      window.dispatchEvent(new CustomEvent('aac:learning-modes-changed', {
        detail: { defaultModeKey: 'roleplay' },
      }))
    })

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Roleplay' })).toBeInTheDocument()
      expect(select).toHaveValue('roleplay')
    })
    expect(modeFetches).toBe(2)
  })

  it('sends the mode key selected in the dropdown to the session start endpoint', async () => {
    render(<Learning />)

    const select = await screen.findByRole('combobox', { name: 'Mode:' })
    await screen.findByRole('option', { name: 'Andaluz' })
    fireEvent.change(select, { target: { value: 'andalusian' } })

    fireEvent.click(screen.getByTestId('topic-card-general'))

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
    fireEvent.click(screen.getByTestId('topic-card-general'))

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
    fireEvent.click(screen.getByTestId('topic-card-general'))

    await waitFor(() => {
      expect(postApi).toHaveBeenCalledWith(
        '/learning/start',
        expect.objectContaining({
          mode_key: 'practice',
          // Topic is an API contract and remains stable across UI locales.
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
    fireEvent.click(screen.getByTestId('topic-card-general'))

    await waitFor(() => {
      expect(postApi).toHaveBeenCalledWith(
        '/learning/start',
        expect.objectContaining({ difficulty: 'advanced' }),
        expect.anything(),
      )
    })
  })
})
