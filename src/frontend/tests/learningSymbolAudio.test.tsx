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
    currentSession: null,
    sessionHistory: [],
    isLoadingHistory: false,
    providerInUse: undefined,
    providerHistory: [],
    startSession,
    submitAnswer,
    submitSymbolAnswer: submitAnswer,
    submitVoiceAnswer,
    fetchSessionHistory: vi.fn(),
    loadSession: vi.fn(),
    askQuestion: vi.fn(),
    endSession: vi.fn(),
    clearError: vi.fn(),
  };
  return {
    useLearningStore: () => mockStore,
    glossSymbolUtterance: (symbols: { label: string }[]) => symbols.map(s => s.label).join(' '),
    __startSession: startSession,
    __submitAnswer: submitAnswer,
    __submitVoiceAnswer: submitVoiceAnswer,
    __mockStore: mockStore,
  };
});

vi.mock('../src/store/authStore', () => ({
  useAuthStore: () => ({ user: { id: 1, user_type: 'teacher', display_name: 'Teacher' } }),
}));

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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en',
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
    
    // Reset store state
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = null;
    store.isLoading = false;

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
      fireEvent.click(screen.getByTitle('Toggle symbol-first view'));
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
    expect(__startSession.mock.calls[0][0].topic).toBe('symbol conversation');
  });

  it('symbol-first: with active session, clicking symbol submits answer', async () => {
    // Mock current session present
    const store = (await import('../src/store/learningStore')).__mockStore;
    store.currentSession = { session_id: 99, success: true, welcome_message: '' } as unknown as LearningSessionResponse;

    render(<Learning />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('Toggle symbol-first view'));
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

  it('audio-first: clicking mic starts default session when none active', async () => {
    render(<Learning />);
    // Click mic button
    const micBtn = screen.getByLabelText(/Start recording/i);
    await act(async () => {
      fireEvent.click(micBtn);
    });
    await waitFor(() => expect(__startSession).toHaveBeenCalled());
    expect(__startSession.mock.calls[0][0].topic).toBe('audio conversation');
  });
});
