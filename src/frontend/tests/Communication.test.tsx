import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import type { Board, BoardSymbol } from '../src/types';

// Hoisted mutable state shared across mocks
const hoisted = vi.hoisted(() => {
  const boardStore = {
    boards: [] as Board[],
    assignedBoards: [] as Board[],
    currentBoard: null as Board | null,
    isListLoading: false,
    isBoardLoading: false,
    error: null as string | null,
    hasMore: false,
    page: 1,
    fetchBoards: vi.fn(),
    fetchAssignedBoards: vi.fn(),
    fetchBoard: vi.fn(),
    setCurrentBoard: (b: Board | null) => {
      boardStore.currentBoard = b;
    },
  };
  const auth = {
    user: {
      id: 1,
      username: 'admin1',
      display_name: 'Admin',
      user_type: 'admin' as const,
      is_active: true,
      created_at: '',
      settings: {} as Record<string, unknown>,
    },
  };
  const learning = {
    submitSymbolAnswer: vi.fn(),
    startSession: vi.fn(),
    resetSession: vi.fn(),
    currentSession: null as { session_id: string } | null,
    isLoading: false,
  };
  const ttsHandlers: {
    cb: ((s: 'idle' | 'speaking') => void) | null;
    status: 'idle' | 'speaking';
  } = { cb: null, status: 'idle' };
  const api = { get: vi.fn(), post: vi.fn(), put: vi.fn() };
  return { boardStore, auth, learning, ttsHandlers, api, addToast: vi.fn() };
});

vi.mock('../src/store/boardStore', () => {
  const useBoardStore = (selector?: (value: typeof hoisted.boardStore) => unknown) =>
    selector ? selector(hoisted.boardStore) : hoisted.boardStore;
  return { useBoardStore };
});

vi.mock('../src/store/authStore', () => {
  const useAuthStore = Object.assign(
    (selector?: (value: typeof hoisted.auth) => unknown) =>
      selector ? selector(hoisted.auth) : hoisted.auth,
    { setState: vi.fn() },
  );
  return { useAuthStore };
});

vi.mock('../src/store/learningStore', () => {
  const useLearningStore = Object.assign(
    (selector?: (value: typeof hoisted.learning) => unknown) =>
      selector ? selector(hoisted.learning) : hoisted.learning,
    { getState: () => hoisted.learning },
  );
  return { useLearningStore };
});

vi.mock('../src/store/toastStore', () => ({
  useToastStore: (selector?: (s: { addToast: typeof hoisted.addToast }) => unknown) => {
    const state = { addToast: hoisted.addToast };
    return selector ? selector(state) : state;
  },
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get: hoisted.api.get,
    post: hoisted.api.post,
    put: hoisted.api.put,
  },
}));

vi.mock('../src/lib/tts', () => ({
  tts: {
    onStatusChange: vi.fn((cb: (s: 'idle' | 'speaking') => void) => {
      hoisted.ttsHandlers.cb = cb;
      return () => {
        hoisted.ttsHandlers.cb = null;
      };
    }),
    getStatus: vi.fn(() => hoisted.ttsHandlers.status),
    enqueue: vi.fn(),
    cancelAll: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'common:noBoardsFound': 'No boards found',
      'common:askTeacherForBoards': 'Ask your teacher to assign you a board.',
      'common:boardLocked': 'Board Locked',
      'common:addOneMoreSymbol': 'Add 1 more symbol to unlock',
      'common:loadMore': 'Load More',
      'common:boardLoadFailed': 'Could not load this board',
      'common:retry': 'Retry',
      'common:selectBoardToStart': 'Select a board to start communicating',
      'common:communication': 'Communication',
      'common:openBoard': 'Open Board',
      'common:symbols': 'symbols',
      'common:backToBoards': 'Back to boards',
      'common:sessionStarted': 'Session started',
      'common:sessionStartFailed': 'Failed to start session',
      'common:sendToChatFailed': 'Could not send the phrase to the assistant',
      'common:attentionPhrase': 'Excuse me!',
    }[key] ?? key),
  }),
}));

vi.mock('lucide-react', () => {
  const Icon = () => null;
  return {
    Search: Icon,
    LayoutGrid: Icon,
    Lock: Icon,
    ArrowLeft: Icon,
    Minimize2: Icon,
    Maximize2: Icon,
    PlusCircle: Icon,
  };
});

// Interactive child mocks so we can drive every page handler
vi.mock('../src/components/board/CommunicationGrid', () => ({
  CommunicationGrid: ({ symbols, onSymbolClick }: {
    symbols: BoardSymbol[];
    onSymbolClick: (s: BoardSymbol) => void;
  }) => (
    <div data-testid="grid">
      {symbols.map((s) => (
        <button key={s.id} onClick={() => onSymbolClick(s)}>
          grid-symbol-{s.symbol.label}
        </button>
      ))}
    </div>
  ),
}));

vi.mock('../src/components/board/SentenceStrip', () => ({
  SentenceStrip: ({ symbols, onRemove, onClear, onBackspace, onSpeak, onSpeakItem, onReorder, onAskAI, isSpeaking }: {
    symbols: BoardSymbol[];
    onRemove: (i: number) => void;
    onClear: () => void;
    onBackspace: () => void;
    onSpeak: () => void;
    onSpeakItem: (t: string) => void;
    onReorder: (a: number, b: number) => void;
    onAskAI: () => void;
    isSpeaking: boolean;
  }) => (
    <div data-testid="sentence-strip">
      {symbols.map((s, i) => (
        <span key={`${s.id}-${i}`} data-testid={`sentence-item-${i}`}>
          {s.custom_text || s.symbol.label}
        </span>
      ))}
      {isSpeaking && <span>is-speaking</span>}
      <button onClick={() => onRemove(0)}>remove-item</button>
      <button onClick={onClear}>clear-sentence</button>
      <button onClick={onBackspace}>backspace-sentence</button>
      <button onClick={onSpeak}>speak-sentence</button>
      <button onClick={() => onSpeakItem('item text')}>speak-item</button>
      <button onClick={() => onReorder(0, 1)}>reorder-sentence</button>
      <button onClick={onAskAI}>ask-ai</button>
    </div>
  ),
}));

vi.mock('../src/components/board/Smartbar', () => ({
  Smartbar: ({ onSelectSymbol }: {
    onSelectSymbol: (s: BoardSymbol) => void;
  }) => (
    <button onClick={() => onSelectSymbol(makeSymbol(99, 'smart'))}>
      smart-select
    </button>
  ),
}));

vi.mock('../src/components/board/CommunicationToolbar', () => ({
  CommunicationToolbar: ({ onHome, onBack, onToggleKeyboard, onToggleChat, onSearch, onContext, onPartnerMic, onQuickResponse, onAttention, isKeyboardOpen, isChatOpen, canGoBack }: {
    onHome: () => void;
    onBack: () => void;
    onToggleKeyboard: () => void;
    onToggleChat: () => void;
    onSearch: () => void;
    onContext: () => void;
    onPartnerMic: () => void;
    onQuickResponse: (t: string) => void;
    onAttention: () => void;
    isKeyboardOpen: boolean;
    isChatOpen: boolean;
    canGoBack: boolean;
  }) => (
    <div data-testid="toolbar">
      <button onClick={onHome}>toolbar-home</button>
      <button onClick={onBack}>toolbar-back</button>
      <button onClick={onToggleKeyboard}>toolbar-keyboard</button>
      <button onClick={onToggleChat}>toolbar-chat</button>
      <button onClick={onSearch}>toolbar-search</button>
      <button onClick={onContext}>toolbar-context</button>
      <button onClick={onPartnerMic}>toolbar-partner</button>
      <button onClick={() => onQuickResponse('quick text')}>quick-response</button>
      <button onClick={onAttention}>attention</button>
      {isKeyboardOpen && <span>keyboard-open</span>}
      {isChatOpen && <span>chat-open</span>}
      {canGoBack && <span>can-go-back</span>}
    </div>
  ),
}));

vi.mock('../src/components/board/KeyboardOverlay', () => ({
  KeyboardOverlay: ({ isOpen, onClose, onSpeak }: {
    isOpen: boolean;
    onClose: () => void;
    onSpeak: (t: string) => void;
  }) => (
    <div>
      {isOpen && <span>keyboard-overlay-open</span>}
      <button onClick={() => onSpeak('keyboard text')}>keyboard-speak</button>
      <button onClick={onClose}>keyboard-close</button>
    </div>
  ),
}));

vi.mock('../src/components/board/CommunicationChat', () => ({
  CommunicationChat: ({ voiceEnabled, onVoiceToggle }: {
    voiceEnabled: boolean;
    onVoiceToggle: () => void;
  }) => (
    <div>
      <span>{voiceEnabled ? 'voice-on' : 'voice-off'}</span>
      <button onClick={onVoiceToggle}>toggle-voice</button>
    </div>
  ),
}));

vi.mock('../src/components/board/SymbolSearchModal', () => ({
  SymbolSearchModal: ({ isOpen, onClose, onSelectSymbol }: {
    isOpen: boolean;
    onClose: () => void;
    onSelectSymbol: (s: BoardSymbol) => void;
  }) => (
    <div>
      {isOpen && <span>search-open</span>}
      <button onClick={() => onSelectSymbol(makeSymbol(98, 'search'))}>
        search-select
      </button>
      <button onClick={onClose}>search-close</button>
    </div>
  ),
}));

vi.mock('../src/components/board/PartnerOverlay', () => ({
  PartnerOverlay: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => (
    <div>
      {isOpen && <span>partner-open</span>}
      <button onClick={onClose}>partner-close</button>
    </div>
  ),
}));

vi.mock('../src/components/learning/BoardsAndTopicsSidebar', () => ({
  BoardsAndTopicsSidebar: ({ isOpen, onToggle, onStartActivity, isStartingSession }: {
    isOpen: boolean;
    onToggle: () => void;
    onStartActivity: (topic: string, purpose: string, boardId?: number) => void;
    isStartingSession: boolean;
  }) => (
    <div>
      {isOpen && <span>boards-open</span>}
      <button onClick={onToggle}>boards-toggle</button>
      <button onClick={() => onStartActivity('general', 'practice', 7)}>
        start-activity
      </button>
      {isStartingSession && <span>starting-session</span>}
    </div>
  ),
}));

import { Communication } from '../src/pages/Communication';

function makeSymbol(id: number, label: string, overrides: Partial<BoardSymbol> = {}): BoardSymbol {
  return {
    id,
    symbol_id: id,
    position_x: 0,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: { id, label, category: 'core' },
    ...overrides,
  };
}

const makeBoard = (overrides: Partial<Board> = {}): Board => ({
  id: 1,
  user_id: 1,
  name: 'Morning Routine',
  description: 'Breakfast and getting ready',
  category: 'daily',
  is_public: false,
  is_template: false,
  created_at: '',
  updated_at: '',
  symbols: [
    makeSymbol(1, 'I'),
    makeSymbol(2, 'want'),
    makeSymbol(3, 'water'),
  ],
  grid_rows: 2,
  grid_cols: 2,
  playable_symbols_count: 3,
  ...overrides,
});

function renderCommunication(initial = '/communication') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Communication />
    </MemoryRouter>,
  );
}

const getTts = async () => (await import('../src/lib/tts')).tts as {
  enqueue: ReturnType<typeof vi.fn>;
  cancelAll: ReturnType<typeof vi.fn>;
  onStatusChange: ReturnType<typeof vi.fn>;
  getStatus: ReturnType<typeof vi.fn>;
};

describe('Communication page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hoisted.boardStore.boards = [makeBoard()];
    hoisted.boardStore.assignedBoards = [];
    hoisted.boardStore.currentBoard = makeBoard();
    hoisted.boardStore.isListLoading = false;
    hoisted.boardStore.isBoardLoading = false;
    hoisted.boardStore.error = null;
    hoisted.boardStore.hasMore = false;
    hoisted.boardStore.page = 1;
    hoisted.auth.user.user_type = 'admin';
    hoisted.auth.user.settings = {};
    hoisted.learning.currentSession = null;
    hoisted.learning.isLoading = false;
    hoisted.learning.startSession.mockReset();
    hoisted.learning.submitSymbolAnswer.mockReset();
    hoisted.api.post.mockResolvedValue({ data: { success: true } });
    hoisted.api.get.mockResolvedValue({ data: [] });
    hoisted.api.put.mockResolvedValue({ data: {} });
  });

  describe('board selection', () => {
    it('loads assigned boards for students and shows role guidance when empty', () => {
      hoisted.auth.user.user_type = 'student';
      hoisted.boardStore.boards = [];
      hoisted.boardStore.assignedBoards = [];
      renderCommunication();

      expect(hoisted.boardStore.fetchAssignedBoards).toHaveBeenCalledWith(1, true);
      expect(screen.getByText('No boards found')).toBeInTheDocument();
      expect(screen.getByText('Ask your teacher to assign you a board.')).toBeInTheDocument();
    });

    it('shows a locked board with the unlock progress and needed count', () => {
      hoisted.boardStore.boards = [
        makeBoard({
          id: 2,
          name: 'Locked Board',
          grid_rows: 4,
          grid_cols: 5,
          playable_symbols_count: 9,
        }),
      ];
      renderCommunication();

      expect(screen.getByText('Locked Board')).toBeInTheDocument();
      expect(screen.getByText('Board Locked')).toBeInTheDocument();
      expect(screen.getByText('Add 1 more symbol to unlock')).toBeInTheDocument();
    });

    it('shows a loading spinner while the list loads', () => {
      hoisted.boardStore.boards = [];
      hoisted.boardStore.isListLoading = true;
      renderCommunication();
      expect(document.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('loads more boards when pagination is available', () => {
      hoisted.boardStore.hasMore = true;
      hoisted.boardStore.page = 1;
      renderCommunication();

      fireEvent.click(screen.getByText('Load More'));
      expect(hoisted.boardStore.fetchBoards).toHaveBeenCalledWith(undefined, undefined, false, 2);
    });
  });

  describe('active board interactions', () => {
    it('opens a playable board and renders the grid', () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      expect(hoisted.boardStore.fetchBoard).toHaveBeenCalledWith(1);
      expect(screen.getByTestId('grid')).toBeInTheDocument();
    });

    it('shows the board loading spinner when no board is loaded yet', () => {
      hoisted.boardStore.isBoardLoading = true;
      hoisted.boardStore.currentBoard = null;
      renderCommunication('/communication?boardId=1');
      expect(document.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('shows a retry state when the board fetch fails', () => {
      hoisted.boardStore.isBoardLoading = false;
      hoisted.boardStore.currentBoard = null;
      hoisted.boardStore.error = 'Failed to fetch board';
      renderCommunication('/communication?boardId=1');

      expect(screen.getByText('Could not load this board')).toBeInTheDocument();
      expect(screen.getByText('Failed to fetch board')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Retry'));
      expect(hoisted.boardStore.fetchBoard).toHaveBeenCalledWith(1, true);
    });

    it('appends a clicked symbol to the sentence and logs usage', async () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-water' }));

      expect(screen.getByTestId('sentence-item-0')).toHaveTextContent('water');
      expect(hoisted.api.post).toHaveBeenCalledWith(
        '/analytics/usage',
        expect.objectContaining({ context_topic: 'communication' }),
      );
      const tts = await getTts();
      expect(tts.enqueue).toHaveBeenCalledWith('water', { key: 3 });
    });

    it('does not speak or log when voice is disabled', async () => {
      hoisted.auth.user.settings = { voice_mode_enabled: false };
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-water' }));

      const tts = await getTts();
      expect(tts.enqueue).not.toHaveBeenCalled();
    });

    it('debounces repeated clicks on the same symbol', () => {
      hoisted.auth.user.settings = { ignore_repeats: 5000 };
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-water' }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-water' }));

      expect(screen.queryByTestId('sentence-item-1')).not.toBeInTheDocument();
    });

    it('navigates to a linked board and back through history', () => {
      hoisted.boardStore.currentBoard = makeBoard({
        symbols: [makeSymbol(1, 'I', { linked_board_id: 5 })],
      });
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));

      expect(hoisted.boardStore.fetchBoard).toHaveBeenCalledWith(5);
      expect(screen.getByText('can-go-back')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'toolbar-back' }));
      expect(hoisted.boardStore.fetchBoard).toHaveBeenCalledWith(1);
    });

    it('goes home when back is pressed with no history', () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'toolbar-back' }));

      expect(screen.getByText('Select a board to start communicating')).toBeInTheDocument();
    });

    it('clears, backspaces, removes and reorders sentence items', () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-want' }));

      fireEvent.click(screen.getByRole('button', { name: 'backspace-sentence' }));
      expect(screen.queryByTestId('sentence-item-1')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-want' }));
      fireEvent.click(screen.getByRole('button', { name: 'reorder-sentence' }));
      expect(screen.getByTestId('sentence-item-0')).toHaveTextContent('want');

      fireEvent.click(screen.getByRole('button', { name: 'remove-item' }));
      expect(screen.queryByTestId('sentence-item-1')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-want' }));
      fireEvent.click(screen.getByRole('button', { name: 'clear-sentence' }));
      expect(screen.queryByTestId('sentence-item-0')).not.toBeInTheDocument();
    });

    it('speaks the sentence when voice is enabled', async () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-want' }));
      fireEvent.click(screen.getByRole('button', { name: 'speak-sentence' }));

      const tts = await getTts();
      expect(tts.enqueue).toHaveBeenCalledWith('I. want');
      expect(hoisted.api.post).toHaveBeenCalledWith(
        '/analytics/usage',
        expect.objectContaining({ context_topic: 'communication' }),
      );
    });

    it('speaks items, quick responses and attention phrases', async () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'speak-item' }));
      fireEvent.click(screen.getByRole('button', { name: 'quick-response' }));
      fireEvent.click(screen.getByRole('button', { name: 'attention' }));
      fireEvent.click(screen.getByRole('button', { name: 'keyboard-speak' }));

      const tts = await getTts();
      expect(tts.cancelAll).toHaveBeenCalled();
      expect(tts.enqueue).toHaveBeenCalledWith('item text');
      expect(tts.enqueue).toHaveBeenCalledWith('quick text');
      expect(tts.enqueue).toHaveBeenCalledWith('Excuse me!');
      expect(tts.enqueue).toHaveBeenCalledWith('keyboard text');
    });

    it('selects symbols from smartbar and search modal', async () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'smart-select' }));
      expect(screen.getByTestId('sentence-item-0')).toHaveTextContent('smart');

      fireEvent.click(screen.getByRole('button', { name: 'search-select' }));
      expect(screen.getByTestId('sentence-item-1')).toHaveTextContent('search');

      const tts = await getTts();
      expect(tts.enqueue).toHaveBeenCalledWith('search', { key: 98 });
    });

    it('toggles the chat panel and voice from within chat', async () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'toolbar-chat' }));
      expect(screen.getByText('chat-open')).toBeInTheDocument();
      expect(screen.getByText('voice-on')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'toggle-voice' }));
      expect(screen.getByText('voice-off')).toBeInTheDocument();
    });

    it('starts a session from the sidebar using the saved default mode', async () => {
      hoisted.auth.user.settings = { default_learning_mode: 'roleplay' };
      hoisted.learning.startSession.mockResolvedValue({});
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'start-activity' }));

      await waitFor(() => {
        expect(hoisted.learning.startSession).toHaveBeenCalledWith(
          expect.objectContaining({ topic: 'general', board_id: 7, mode_key: 'roleplay' }),
          1,
        );
        expect(hoisted.addToast).toHaveBeenCalledWith('Session started', 'success');
        expect(hoisted.boardStore.fetchBoard).toHaveBeenCalledWith(7);
      });
    });

    it('shows an error toast when starting a session fails', async () => {
      hoisted.learning.startSession.mockRejectedValue(new Error('boom'));
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'start-activity' }));

      await waitFor(() => {
        expect(hoisted.addToast).toHaveBeenCalledWith('Failed to start session', 'error');
      });
    });

    it('sends the sentence to chat starting a new session', async () => {
      hoisted.learning.startSession.mockImplementation(async () => {
        hoisted.learning.currentSession = { session_id: 's1' };
      });
      hoisted.learning.submitSymbolAnswer.mockResolvedValue({});
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));
      fireEvent.click(screen.getByRole('button', { name: 'ask-ai' }));

      await waitFor(() => {
        expect(hoisted.learning.startSession).toHaveBeenCalled();
        expect(hoisted.learning.submitSymbolAnswer).toHaveBeenCalledWith(
          's1',
          expect.arrayContaining([expect.objectContaining({ id: 1 })]),
          expect.any(String),
          expect.any(String),
        );
      });
    });

    it('sends to chat directly when a session already exists', async () => {
      hoisted.learning.currentSession = { session_id: 'existing' };
      hoisted.learning.submitSymbolAnswer.mockResolvedValue({});
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));
      fireEvent.click(screen.getByRole('button', { name: 'ask-ai' }));

      await waitFor(() => {
        expect(hoisted.learning.startSession).not.toHaveBeenCalled();
        expect(hoisted.learning.submitSymbolAnswer).toHaveBeenCalledWith(
          'existing',
          expect.arrayContaining([expect.objectContaining({ id: 1 })]),
          expect.any(String),
          expect.any(String),
        );
      });
    });

    it('reflects the TTS speaking status in the sentence strip', async () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      expect(screen.queryByText('is-speaking')).not.toBeInTheDocument();

      act(() => {
        hoisted.ttsHandlers.cb?.('speaking');
      });
      expect(screen.getByText('is-speaking')).toBeInTheDocument();
    });

    it('initializes the speaking state from the TTS queue on mount (no stale stuck state)', async () => {
      // Simulate the module-singleton TTS queue already speaking when the page
      // mounts (e.g. a symbol was tapped just before navigating back to this
      // page). The page must reflect `speaking` immediately instead of waiting
      // for a later status transition, so the speak control is never left
      // enabled while speech is (or was just) in flight.
      hoisted.ttsHandlers.status = 'speaking';
      renderCommunication();
      // The sentence strip (and therefore the speaking indicator) renders
      // once a board is selected.
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      expect(screen.getByText('is-speaking')).toBeInTheDocument();

      // The queue later reports idle; the page follows and the control unlocks.
      act(() => {
        hoisted.ttsHandlers.cb?.('idle');
      });
      expect(screen.queryByText('is-speaking')).not.toBeInTheDocument();
    });

    it('requests fullscreen and updates on fullscreenchange', () => {
      const requestFullscreen = vi.fn(() => Promise.resolve());
      const exitFullscreen = vi.fn(() => Promise.resolve());
      Object.defineProperty(document, 'fullscreenElement', { value: null, configurable: true });
      Object.defineProperty(document.documentElement, 'requestFullscreen', {
        value: requestFullscreen,
        configurable: true,
      });
      Object.defineProperty(document, 'exitFullscreen', { value: exitFullscreen, configurable: true });

      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'toolbar-keyboard' }));
      expect(screen.getByText('keyboard-open')).toBeInTheDocument();

      // The header fullscreen button has a title
      const fullscreenBtn = screen.getByTitle('enterFullscreen');
      fireEvent.click(fullscreenBtn);
      expect(requestFullscreen).toHaveBeenCalled();

      Object.defineProperty(document, 'fullscreenElement', { value: {}, configurable: true });
      fireEvent(document, new Event('fullscreenchange'));
      expect(screen.getByTitle('exitFullscreen')).toBeInTheDocument();
    });

    it('exits fullscreen when already fullscreen', () => {
      const exitFullscreen = vi.fn(() => Promise.resolve());
      Object.defineProperty(document, 'fullscreenElement', { value: {}, configurable: true });
      Object.defineProperty(document, 'exitFullscreen', { value: exitFullscreen, configurable: true });

      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByTitle('enterFullscreen'));
      expect(exitFullscreen).toHaveBeenCalled();
    });

    it('opens and closes the search, partner, keyboard and boards panels', () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));

      fireEvent.click(screen.getByRole('button', { name: 'toolbar-search' }));
      expect(screen.getByText('search-open')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'search-close' }));
      expect(screen.queryByText('search-open')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'toolbar-partner' }));
      expect(screen.getByText('partner-open')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'partner-close' }));
      expect(screen.queryByText('partner-open')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'toolbar-keyboard' }));
      expect(screen.getByText('keyboard-overlay-open')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'keyboard-close' }));
      expect(screen.queryByText('keyboard-overlay-open')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'toolbar-context' }));
      expect(screen.getByText('boards-open')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'boards-toggle' }));
      expect(screen.queryByText('boards-open')).not.toBeInTheDocument();
    });

    it('counts symbols from the symbols array when playable_symbols_count is absent', () => {
      hoisted.boardStore.boards = [
        makeBoard({ playable_symbols_count: undefined as unknown as number }),
      ];
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      expect(screen.getByTestId('grid')).toBeInTheDocument();
    });

    it('does nothing on speak and chat when the sentence is empty', async () => {
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'speak-sentence' }));
      fireEvent.click(screen.getByRole('button', { name: 'ask-ai' }));

      await new Promise((r) => setTimeout(r, 50));
      expect(hoisted.learning.startSession).not.toHaveBeenCalled();
      expect(hoisted.learning.submitSymbolAnswer).not.toHaveBeenCalled();
      const tts = await getTts();
      expect(tts.enqueue).not.toHaveBeenCalled();
    });

    it('returns silently from chat when starting the session fails', async () => {
      hoisted.learning.startSession.mockRejectedValue(new Error('no session'));
      renderCommunication();
      fireEvent.click(screen.getByRole('button', { name: /Morning Routine/i }));
      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));
      fireEvent.click(screen.getByRole('button', { name: 'ask-ai' }));

      await waitFor(() => {
        expect(hoisted.learning.startSession).toHaveBeenCalled();
        expect(hoisted.learning.submitSymbolAnswer).not.toHaveBeenCalled();
      });
    });

    it('skips fetching and session actions when no user is present', () => {
      hoisted.auth.user = null as unknown as typeof hoisted.auth.user;
      hoisted.boardStore.currentBoard = makeBoard();
      renderCommunication('/communication?boardId=1');

      expect(hoisted.boardStore.fetchBoards).not.toHaveBeenCalled();
      expect(hoisted.boardStore.fetchAssignedBoards).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'start-activity' }));
      expect(hoisted.learning.startSession).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'grid-symbol-I' }));
      fireEvent.click(screen.getByRole('button', { name: 'ask-ai' }));
      expect(hoisted.learning.submitSymbolAnswer).not.toHaveBeenCalled();
    });
  });
});
