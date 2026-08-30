import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CommunicationChat } from '../src/components/board/CommunicationChat';

// jsdom does not implement scrollIntoView.
Element.prototype.scrollIntoView = vi.fn();

const hoisted = vi.hoisted(() => {
  const learning = {
    messages: [] as Array<{ role: string; content: string }>,
    isLoading: false,
    currentSession: null as { session_id: string } | null,
    startSession: vi.fn(),
    submitAnswer: vi.fn(),
    submitVoiceAnswer: vi.fn(),
    showAdminReasoning: false,
    error: null as string | null,
  };
  const auth = {
    user: { id: 1, username: 'admin1', display_name: 'Admin', user_type: 'admin', settings: {} },
  };
  const addToast = vi.fn();
  const voiceRecorder = {
    isRecording: false,
    hasRecording: false,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    discardRecording: vi.fn(),
    sendRecording: vi.fn(),
  };
  return { learning, auth, addToast, voiceRecorder };
});

vi.mock('../src/store/learningStore', () => {
  const useLearningStore = Object.assign(
    (selector?: (value: typeof hoisted.learning) => unknown) =>
      selector ? selector(hoisted.learning) : hoisted.learning,
    { getState: () => hoisted.learning },
  );
  return {
    useLearningStore,
    stripReasoning: (text: string) => text,
  };
});

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (value: typeof hoisted.auth) => unknown) =>
    selector ? selector(hoisted.auth) : hoisted.auth,
}));

vi.mock('../src/store/toastStore', () => ({
  useToastStore: (selector?: (s: { addToast: typeof hoisted.addToast }) => unknown) => {
    const state = { addToast: hoisted.addToast };
    return selector ? selector(state) : state;
  },
}));

vi.mock('../src/lib/tts', () => ({
  tts: { enqueue: vi.fn(), cancelAll: vi.fn() },
}));

vi.mock('../src/components/learning/useVoiceRecorder', () => ({
  useVoiceRecorder: () => hoisted.voiceRecorder,
}));

vi.mock('react-i18next', () => {
  const table: Record<string, string> = {
    typeAnswer: 'Type your answer...',
    aiAssistant: 'AI Assistant',
    conversationPartner: 'Conversation Partner',
    startChatting: 'Start chatting using the board or type here.',
    voiceOn: 'Voice On',
    voiceOff: 'Voice Off',
    errorPrefix: 'Error: {{message}}',        'common:sessionStartFailed': 'Could not start the conversation session',

  };
  return {
    useTranslation: () => ({
      t: (key: string, defaultValue?: string | Record<string, string>, options?: Record<string, string>) => {
        const interpolation = typeof defaultValue === 'object' ? defaultValue : options;
        const base = table[key] ?? (typeof defaultValue === 'string' ? defaultValue : undefined) ?? key;
        let text = base;
        for (const [name, value] of Object.entries(interpolation || {})) {
          text = text.replace(`{{${name}}}`, value);
        }
        return text;
      },
      i18n: { exists: () => false, language: 'es-ES' },
    }),
  };
});

function renderChat(
  overrides: Partial<typeof hoisted.learning> = {},
  boardName = 'Practice Board',
  voiceEnabled = false,
) {
  Object.assign(hoisted.learning, {
    messages: [],
    isLoading: false,
    currentSession: null,
    startSession: vi.fn().mockResolvedValue({}),
    submitAnswer: vi.fn().mockResolvedValue({}),
    submitVoiceAnswer: vi.fn().mockResolvedValue({}),
    showAdminReasoning: false,
    error: null,
    ...overrides,
  });
  return render(
    <CommunicationChat
      voiceEnabled={voiceEnabled}
      onVoiceToggle={() => {}}
      boardId={7}
      boardName={boardName}
    />,
  );
}

const getTts = async () => (await import('../src/lib/tts')).tts as {
  enqueue: ReturnType<typeof vi.fn>;
  cancelAll: ReturnType<typeof vi.fn>;
};

describe('CommunicationChat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the store error so a failed exchange is not silent', () => {
    renderChat({ error: 'The provider did not respond' });
    expect(screen.getByText('Error: The provider did not respond')).toBeInTheDocument();
  });

  it('does not show an error banner when there is no error', () => {
    renderChat();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('starts a session on demand when sending with no active session', async () => {
    renderChat({ currentSession: null });
    // The on-demand start must materialize a session that the send then uses.
    hoisted.learning.startSession.mockImplementation(async () => {
      hoisted.learning.currentSession = { session_id: 'sess-1' };
    });
    hoisted.learning.submitAnswer.mockResolvedValue({});

    const input = screen.getByPlaceholderText('Type your answer...');
    fireEvent.change(input, { target: { value: 'hola' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(hoisted.learning.startSession).toHaveBeenCalled();
      expect(hoisted.learning.submitAnswer).toHaveBeenCalledWith('sess-1', 'hola');
    });
  });

  it('uses the active board as the conversation topic', async () => {
    renderChat();

    const input = screen.getByPlaceholderText('Type your answer...');
    fireEvent.change(input, { target: { value: 'hola' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(hoisted.learning.startSession).toHaveBeenCalledWith(
        expect.objectContaining({
          topic: 'Practice Board',
          board_id: 7,
        }),
        1,
      );
    });
  });

  it('shows a toast when starting a session for a message fails', async () => {
    renderChat({ currentSession: null });
    hoisted.learning.startSession.mockRejectedValue(new Error('down'));

    const input = screen.getByPlaceholderText('Type your answer...');
    fireEvent.change(input, { target: { value: 'hola' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(hoisted.addToast).toHaveBeenCalledWith(
        'Could not start the conversation session',
        'error',
      );
    });
    expect(hoisted.learning.submitAnswer).not.toHaveBeenCalled();
  });

  it('speaks feedback appended after a user message', async () => {
    const { rerender } = renderChat({
      currentSession: { session_id: 'sess-1' },
      messages: [{ role: 'assistant', content: 'Welcome' }],
    }, 'Practice Board', true);
    const tts = await getTts();

    expect(tts.enqueue).toHaveBeenCalledWith('Welcome', { rate: 0.9 });
    tts.enqueue.mockClear();

    hoisted.learning.messages = [
      { role: 'assistant', content: 'Welcome' },
      { role: 'user', content: 'Hola' },
      { role: 'assistant', content: 'Good answer' },
    ];
    rerender(
      <CommunicationChat
        voiceEnabled={true}
        onVoiceToggle={() => {}}
        boardId={7}
        boardName="Practice Board"
      />,
    );

    expect(tts.enqueue).toHaveBeenCalledWith('Good answer', { rate: 0.9 });
  });

  it('restarts speech tracking for a new session with the same first message', async () => {
    const { rerender } = renderChat({
      currentSession: { session_id: 'sess-1' },
      messages: [{ role: 'assistant', content: 'Welcome' }],
    }, 'Practice Board', true);
    const tts = await getTts();

    expect(tts.enqueue).toHaveBeenCalledWith('Welcome', { rate: 0.9 });
    tts.enqueue.mockClear();

    hoisted.learning.currentSession = { session_id: 'sess-2' };
    rerender(
      <CommunicationChat
        voiceEnabled
        onVoiceToggle={() => {}}
        boardId={7}
        boardName="Practice Board"
      />,
    );

    expect(tts.enqueue).toHaveBeenCalledWith('Welcome', { rate: 0.9 });
  });
});
