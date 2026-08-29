import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { LearningSessionResponse } from '../src/types';

vi.mock('../src/store/learningStore', () => {
  const startSession = vi.fn();
  const submitAnswer = vi.fn();
  const submitVoiceAnswer = vi.fn();
  const mockStore = {
    messages: [],
    isLoading: false,
    error: null,
    currentSession: null,
    currentQuestion: null,
    lastAnswer: null,
    revealedAnswer: null,
    progressStats: null,
    lastSessionSummary: null,
    sessionHistory: [],
    isLoadingHistory: false,
    providerInUse: undefined,
    providerHistory: [],
    showAdminReasoning: false,
    setShowAdminReasoning: vi.fn(),
    startSession,
    submitAnswer,
    submitSymbolAnswer: submitAnswer,
    submitVoiceAnswer,
    fetchSessionHistory: vi.fn(),
    loadSession: vi.fn(),
    askQuestion: vi.fn(),
    askNextQuestion: vi.fn(),
    endSession: vi.fn(),
    clearError: vi.fn(),
    clearSessionSummary: vi.fn(),
    autoAskEnabled: true,
    setAutoAskEnabled: vi.fn(),
    difficultyOverride: 'adaptive',
    setDifficultyOverride: vi.fn(),
  };
  return {
    useLearningStore: Object.assign(
      (selector?: (state: typeof mockStore) => unknown) =>
        selector ? selector(mockStore) : mockStore,
      { getState: () => mockStore },
    ),
    glossSymbolUtterance: (symbols: { label: string }[]) => symbols.map(s => s.label).join(' '),
    stripReasoning: (text: string) => text,
    __startSession: startSession,
    __submitAnswer: submitAnswer,
    __submitVoiceAnswer: submitVoiceAnswer,
    __mockStore: mockStore,
  };
});

vi.mock('../src/store/authStore', () => {
  const state = { user: { id: 1, user_type: 'teacher', display_name: 'Teacher' } };
  const useAuthStore = Object.assign(
    (selector?: (value: typeof state) => unknown) =>
      selector ? selector(state) : state,
    { setState: vi.fn() },
  );
  return { useAuthStore };
});

vi.mock('../src/lib/api', () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    },
  };
});

const { mockTtsEnqueue, mockLanguage } = vi.hoisted(() => ({
  mockTtsEnqueue: vi.fn(),
  mockLanguage: { value: 'en' },
}));
vi.mock('../src/lib/tts', () => ({
  tts: {
    enqueue: mockTtsEnqueue,
  },
}));

// Helper to access the mocked api module
const getMockedApi = async () =>
  (await import('../src/lib/api')).default as { get: Mock; post: Mock };

// Stub MediaRecorder for audio-first test
class MockMediaRecorder {
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  stream: unknown;
  constructor(stream: unknown) {
    this.stream = stream;
  }
  start() {}
  stop() {
    this.onstop?.();
  }
}

// Import after mocks
import { Learning } from '../src/pages/Learning';
import { __startSession, __submitAnswer } from '../src/store/learningStore';

// A stable t identity matters: Learning's modes effect depends on `t`, and
// react-i18next memoizes t across renders. A fresh arrow per render would
// re-run the effect (and its fetch) on every render.
const stableT = (key: string) => key;

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: stableT,
    i18n: {
      language: mockLanguage.value,
      changeLanguage: () => new Promise(() => {}),
    },
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
}));

describe('Learning symbol-first and audio-first flows', () => {
  beforeEach(async () => {
    const api = (await import('../src/lib/api')).default;
    api.get.mockReset?.();
    api.post?.mockReset?.();
    api.put?.mockResolvedValue({ data: {} });
    api.get.mockImplementation((url: string) => {
      if (url === '/learning-modes/' || url.startsWith('/learning-modes/')) {
        return Promise.resolve({
          data: [{ id: 1, name: 'Vocabulary Practice', key: 'practice', description: '' }],
        });
      }
      if (url === '/boards/symbols' || url.startsWith('/boards/symbols')) {
        return Promise.resolve({
          data: [{ id: 10, label: 'Hello', category: 'greeting', image_path: '/uploads/symbols/test.png' }],
        });
      }
      if (url === '/boards/' || url.startsWith('/boards/')) {
        return Promise.resolve({
          data: [{ id: 8, name: 'Test Board', description: '', category: 'general', user_id: 1, symbols: [], created_at: '', updated_at: '' }],
        });
      }
      return Promise.resolve({ data: [] });
    });
    api.post?.mockResolvedValue({ data: [] });
    __startSession.mockReset();
    __submitAnswer.mockReset();
    mockTtsEnqueue.mockReset();
    mockLanguage.value = 'en';
    
    // Reset store state
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = null;
    store.isLoading = false;
    store.messages = [];
    store.providerHistory = [];
    store.sessionHistory = [];
    store.isLoadingHistory = false;
    store.lastSessionSummary = null;
    store.askQuestion.mockReset();
    store.endSession.mockReset();
    store.loadSession.mockReset();

    (globalThis as unknown as { navigator: { mediaDevices: unknown } }).navigator.mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue({
        getTracks: () => [{ stop: vi.fn() }],
      }),
    };
    (globalThis as unknown as { MediaRecorder: typeof MockMediaRecorder }).MediaRecorder = MockMediaRecorder;
  });

  it('symbol-first: clicking symbol starts session when none active', async () => {
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });
    const api = await getMockedApi();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    const hello = await screen.findByText('Hello');
    await act(async () => {
      fireEvent.click(hello);
    });
    
    // Click Send
    const sendBtn = screen.getByText('sendSymbols');
    await act(async () => {
      fireEvent.click(sendBtn);
    });

    await waitFor(() => expect(__startSession).toHaveBeenCalled());
    expect(__startSession.mock.calls[0][0].topic).toBe('topics.symbolConversation');
  });

  it('symbol-first: with active session, clicking symbol submits answer', async () => {
    // Mock current session present
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;

    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });
    const api2 = await getMockedApi();
    await waitFor(() => expect(api2.get).toHaveBeenCalled());
    const hello = await screen.findByText('Hello');
    await act(async () => {
      fireEvent.click(hello);
    });

    // Click Send
    const sendBtn = screen.getByText('sendSymbols');
    await act(async () => {
      fireEvent.click(sendBtn);
    });

    await waitFor(() => expect(__submitAnswer).toHaveBeenCalled());
    expect(__submitAnswer).toHaveBeenCalledWith(
        99, 
        expect.arrayContaining([expect.objectContaining({ label: 'Hello' })]), 
        'Hello.', 
        'Hello'
    );

    // reset
    store.currentSession = null;
  });

  it('symbol-first: Speak only uses the shared TTS queue with the active locale', async () => {
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });
    await waitFor(() => expect(screen.getByText('Hello')).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByText('Hello'));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText('speakOnly'));
    });

    expect(mockTtsEnqueue).toHaveBeenCalledWith('Hello.', {
      rate: 0.9,
      lang: 'en-US',
    });
  });

  it('symbol-first: Speak only passes the Spanish locale to the shared TTS queue', async () => {
    mockLanguage.value = 'es';
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });
    await waitFor(() => expect(screen.getByText('Hello')).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByText('Hello'));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText('speakOnly'));
    });

    expect(mockTtsEnqueue).toHaveBeenCalledWith('Hello.', {
      rate: 0.9,
      lang: 'es-ES',
    });
  });

  it('audio-first: clicking mic starts default session when none active', async () => {
    render(<Learning />);
    // Click mic button
    const micBtn = screen.getByLabelText(/startRecordingLabel/i);
    await act(async () => {
      fireEvent.click(micBtn);
    });
    await waitFor(() => expect(__startSession).toHaveBeenCalled());
    expect(__startSession.mock.calls[0][0].topic).toBe('topics.audioConversation');
  });

  it('chat: sends a typed answer when a session is active', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;

    render(<Learning />);
    const input = screen.getByPlaceholderText('typeAnswer');
    fireEvent.change(input, { target: { value: 'Red and blue' } });
    fireEvent.submit(input.closest('form') as HTMLFormElement);

    await waitFor(() => expect(__submitAnswer).toHaveBeenCalledWith(99, 'Red and blue'));
  });

  it('chat: asks to start a session first when none is active', async () => {
    render(<Learning />);
    const input = screen.getByPlaceholderText('typeAnswer');
    fireEvent.change(input, { target: { value: 'Hello' } });
    fireEvent.submit(input.closest('form') as HTMLFormElement);

    expect(await screen.findByText('errors.startSessionFirst')).toBeInTheDocument();
    expect(__submitAnswer).not.toHaveBeenCalled();
  });

  it('chat: requests a new question manually for an active session', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;

    render(<Learning />);
    fireEvent.click(await screen.findByRole('button', { name: 'newQuestion' }));

    await waitFor(() => expect(store.askQuestion).toHaveBeenCalledWith(99, undefined));
  });

  it('chat: ends the session through the confirmation dialog', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;

    render(<Learning />);
    fireEvent.click(await screen.findByRole('button', { name: 'endSession' }));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getAllByRole('button', { name: 'endSession' })[1]);

    await waitFor(() => expect(store.endSession).toHaveBeenCalledWith(99));
  });

  it('history: loads a past session from the history panel', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.sessionHistory = [
      {
        id: 5,
        topic: 'Colors',
        created_at: '2026-01-01T00:00:00Z',
        status: 'completed',
        comprehension_score: 0.8,
      },
    ];

    render(<Learning />);
    fireEvent.click(screen.getByText('showHistory'));
    fireEvent.click(await screen.findByTestId('learning-history-item'));

    await waitFor(() => expect(store.loadSession).toHaveBeenCalledWith(5));
  });

  it('header: announces a provider switch from the provider history', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.providerHistory = [{ provider: 'openrouter', model: 'gpt-4o-mini' }];

    render(<Learning />);

    expect(await screen.findByText('providerSwitched')).toBeInTheDocument();
  });

  it('voice: explicitly speaks the welcome message returned when starting a session', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    const welcome = 'Hola, Admin 1787327487883. Hoy vamos a practicar Conversación General.';
    store.startSession.mockImplementation(async () => {
      store.currentSession = { session_id: 12, success: true, welcome_message: welcome };
      store.messages = [{ role: 'assistant', content: welcome }];
    });

    render(<Learning />);
    fireEvent.click(screen.getByTestId('learning-session-start'));

    await waitFor(() => expect(mockTtsEnqueue).toHaveBeenCalledWith(welcome, { rate: 0.9 }));
    expect(screen.getByText(welcome)).toBeInTheDocument();
  });

  it('voice: speaks the last assistant message through the TTS queue', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.messages = [{ role: 'assistant', content: 'Hello there' }];

    render(<Learning />);

    await waitFor(() => expect(mockTtsEnqueue).toHaveBeenCalledWith('Hello there', { rate: 0.9 }));
  });

  it('voice: replays the first message when a new session has the same greeting', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 1, success: true, welcome_message: '' } as unknown as LearningSessionResponse;
    store.messages = [{ role: 'assistant', content: 'Hello there' }];

    const { rerender } = render(<Learning />);
    await waitFor(() => expect(mockTtsEnqueue).toHaveBeenCalledTimes(1));

    store.currentSession = { session_id: 2, success: true, welcome_message: '' } as unknown as LearningSessionResponse;
    rerender(<Learning />);
    await waitFor(() => expect(mockTtsEnqueue).toHaveBeenCalledTimes(2));
  });

  it('voice: ignores non-assistant messages for TTS', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.messages = [{ role: 'user', content: 'Hello there' }];

    render(<Learning />);

    await waitFor(() => expect(screen.getByText('Hello there')).toBeInTheDocument());
    expect(mockTtsEnqueue).not.toHaveBeenCalled();
  });

  it('chat: ignores an empty message', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;

    render(<Learning />);
    const input = screen.getByPlaceholderText('typeAnswer');
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.submit(input.closest('form') as HTMLFormElement);

    await waitFor(() => expect(__submitAnswer).not.toHaveBeenCalled());
  });

  it('chat: does not request a question while loading', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;
    store.isLoading = true;

    render(<Learning />);
    fireEvent.click(await screen.findByRole('button', { name: 'newQuestion' }));

    expect(store.askQuestion).not.toHaveBeenCalled();
  });

  it('chat: does not end the session while loading', async () => {
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;
    store.isLoading = true;

    render(<Learning />);
    fireEvent.click(await screen.findByRole('button', { name: 'endSession' }));

    expect(store.endSession).not.toHaveBeenCalled();
  });

  it('symbol-first: shows a failure when the session does not start', async () => {
    render(<Learning />);
    fireEvent.click(screen.getByTitle('toggleSymbolView'));
    const hello = await screen.findByText('Hello');
    fireEvent.click(hello);
    fireEvent.click(screen.getByText('sendSymbols'));

    expect(await screen.findByText('errors.sessionStartFailed')).toBeInTheDocument();
  });

  it('symbol-first: falls back to an empty list when symbols fail to load', async () => {
    const api = await getMockedApi();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') return Promise.reject(new Error('offline'));
      return Promise.resolve({ data: [] });
    });
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });

    expect(await screen.findByPlaceholderText('search')).toBeInTheDocument();
    expect(screen.queryByText('Hello')).not.toBeInTheDocument();
  });

  it('symbol-first: filters symbols by search text and core words', async () => {
    const api = await getMockedApi();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') {
        return Promise.resolve({
          data: [
            { id: 10, label: 'I', category: 'pronoun', image_path: '/uploads/symbols/i.png' },
            { id: 11, label: 'Hello', category: 'greeting', image_path: null },
            { id: 12, label: 'Bye', category: 'greeting', image_path: null },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });

    const search = await screen.findByPlaceholderText('search');
    await act(async () => {
      fireEvent.change(search, { target: { value: 'hello' } });
    });
    // The core-words row always shows priority words like "I".
    expect(screen.getByText('I')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Bye')).not.toBeInTheDocument());
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('symbol-first: removes and clears symbols from the utterance', async () => {
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });
    const hello = await screen.findByText('Hello');
    await act(async () => {
      fireEvent.click(hello);
    });

    await act(async () => {
      fireEvent.click(screen.getByLabelText('removeSymbolLabel'));
    });
    expect(screen.queryByLabelText('removeSymbolLabel')).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(hello);
    });
    await act(async () => {
      fireEvent.click(screen.getByText('clear'));
    });
    expect(screen.queryByLabelText('removeSymbolLabel')).not.toBeInTheDocument();
  });

  it('header: toggles voice input', async () => {
    render(<Learning />);

    fireEvent.click(await screen.findByTitle('disableVoice'));

    expect(await screen.findByTitle('enableVoice')).toBeInTheDocument();
  });

  it('symbol-first: filters by the food category including drinks', async () => {
    const api = await getMockedApi();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') {
        return Promise.resolve({
          data: [
            { id: 10, label: 'Apple', category: 'food', image_path: null },
            { id: 11, label: 'Water', category: 'drinks', image_path: null },
            { id: 12, label: 'Hello', category: 'greeting', image_path: null },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });

    await screen.findByText('Apple');
    await act(async () => {
      fireEvent.click(screen.getByText('categories.food'));
    });

    await waitFor(() => expect(screen.queryByText('Hello')).not.toBeInTheDocument());
    expect(screen.getByText('Apple')).toBeInTheDocument();
    expect(screen.getByText('Water')).toBeInTheDocument();
  });

  it('symbol-first: prefetches the library on page load without opening the view', async () => {
    const api = await getMockedApi();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') {
        return Promise.resolve({
          data: [{ id: 10, label: 'Hello', category: 'greeting', image_path: '/uploads/symbols/test.png' }],
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<Learning />);

    // The library is fetched in the background as soon as the page mounts,
    // before the symbol view is ever opened.
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        '/boards/symbols',
        expect.objectContaining({ params: expect.objectContaining({ limit: 1000 }) }),
      ),
    );
    // The view is still closed; the data is simply ready for when it opens.
    expect(screen.queryByPlaceholderText('search')).not.toBeInTheDocument();
    expect(screen.queryByText('Hello')).not.toBeInTheDocument();
  });

  it('symbol-first: opening the view does not refetch an already loaded library', async () => {
    const api = await getMockedApi();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') {
        return Promise.resolve({
          data: [{ id: 10, label: 'Hello', category: 'greeting', image_path: '/uploads/symbols/test.png' }],
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<Learning />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/boards/symbols', expect.anything()));

    // Opening the view uses the prefetched data: the library is requested
    // exactly once (by the mount prefetch), never again on open.
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });
    expect(await screen.findByText('Hello')).toBeInTheDocument();
    const symbolFetches = api.get.mock.calls.filter((call) => call[0] === '/boards/symbols');
    expect(symbolFetches).toHaveLength(1);
  });

  it('symbol-first: orders core words by priority', async () => {
    const api = await getMockedApi();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') {
        return Promise.resolve({
          data: [
            { id: 10, label: 'want', category: 'verb', image_path: null },
            { id: 11, label: 'I', category: 'pronoun', image_path: '/uploads/symbols/i.png' },
            { id: 12, label: 'zebra', category: 'animal', image_path: null },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('toggleSymbolView'));
    });

    await screen.findAllByText('I');
    await screen.findAllByText('want');
    const coreButtons = screen.getAllByRole('button').filter((button) =>
      ['I', 'want'].includes(button.textContent ?? ''),
    );
    // The core-words row renders before the symbol grid, so its two entries
    // come first and must follow the priority order (I before want).
    expect(coreButtons.slice(0, 2).map((button) => button.textContent)).toEqual(['I', 'want']);
  });
});
