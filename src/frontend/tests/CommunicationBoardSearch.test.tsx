import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Board } from '../src/types';

const boardStoreState = vi.hoisted(() => ({
  boards: [] as Board[],
  assignedBoards: [] as Board[],
  fetchBoards: vi.fn(),
  fetchAssignedBoards: vi.fn(),
}));

const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    username: 'admin1',
    display_name: 'Admin',
    user_type: 'admin' as const,
    is_active: true,
    created_at: '',
  },
}));

vi.mock('../src/store/boardStore', () => {
  const useBoardStore = (selector?: (value: typeof boardStoreState & {
    currentBoard: null;
    fetchBoard: ReturnType<typeof vi.fn>;
    isLoading: boolean;
    isListLoading: boolean;
    isBoardLoading: boolean;
    hasMore: boolean;
    page: number;
  }) => unknown) => {
    const state = {
      ...boardStoreState,
      currentBoard: null,
      fetchBoard: vi.fn(),
      isLoading: false,
      isListLoading: false,
      isBoardLoading: false,
      hasMore: false,
      page: 1,
    };
    return selector ? selector(state) : state;
  };
  return { useBoardStore };
});

vi.mock('../src/store/authStore', () => {
  const useAuthStore = (selector?: (value: typeof authState) => unknown) =>
    selector ? selector(authState) : authState;
  return { useAuthStore };
});

vi.mock('../src/store/learningStore', () => {
  const state = {
    submitSymbolAnswer: vi.fn(),
    startSession: vi.fn(),
    resetSession: vi.fn(),
    currentSession: null,
    isLoading: false,
  };
  const useLearningStore = Object.assign(
    (selector?: (value: typeof state) => unknown) => selector ? selector(state) : state,
    { getState: vi.fn() },
  );
  return { useLearningStore };
});

vi.mock('../src/store/toastStore', () => ({
  useToastStore: () => ({ addToast: vi.fn() }),
}));

vi.mock('../src/lib/api', () => ({
  default: {
    post: vi.fn(),
  },
}));

vi.mock('../src/lib/tts', () => ({
  tts: {
    onStatusChange: vi.fn(() => () => {}),
    getStatus: vi.fn(() => 'idle'),
    enqueue: vi.fn(),
    cancelAll: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>) => {
      if (typeof arg2 === 'string') return arg2;
      const values: Record<string, string> = {
        'common:communication': 'Communication',
        'common:selectBoardToStart': 'Select a board to start communicating',
        'common:searchBoards': 'Search boards...',
        'common:noBoardsMatchSearch': 'No boards match your search',
        'common:noBoardsFound': 'No boards found',
        'common:createBoardFirst': 'Create a board in the Boards section first.',
        'common:askTeacherForBoards': 'Ask your teacher to assign you a board.',
        'common:openBoard': 'Open Board',
        'common:symbols': 'symbols',
      };
      return values[key] ?? key;
    },
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

vi.mock('../src/components/board/CommunicationGrid', () => ({
  CommunicationGrid: () => null,
}));
vi.mock('../src/components/board/SentenceStrip', () => ({
  SentenceStrip: () => null,
}));
vi.mock('../src/components/board/Smartbar', () => ({
  Smartbar: () => null,
}));
vi.mock('../src/components/board/CommunicationToolbar', () => ({
  CommunicationToolbar: () => null,
}));
vi.mock('../src/components/board/KeyboardOverlay', () => ({
  KeyboardOverlay: () => null,
}));
vi.mock('../src/components/board/CommunicationChat', () => ({
  CommunicationChat: () => null,
}));
vi.mock('../src/components/board/SymbolSearchModal', () => ({
  SymbolSearchModal: () => null,
}));
vi.mock('../src/components/board/PartnerOverlay', () => ({
  PartnerOverlay: () => null,
}));
vi.mock('../src/components/learning/BoardsAndTopicsSidebar', () => ({
  BoardsAndTopicsSidebar: () => null,
}));

vi.mock('../src/hooks/useTopicPickerPool', () => ({
  useTopicPickerPool: () => ({ pickerTopics: [], pickerRecent: [] }),
}));

import { Communication } from '../src/pages/Communication';

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
  symbols: [],
  grid_rows: 2,
  grid_cols: 2,
  playable_symbols_count: 2,
  ...overrides,
});

function renderCommunication() {
  return render(
    <MemoryRouter initialEntries={['/communication']}>
      <Communication />
    </MemoryRouter>,
  );
}

describe('Communication board selection search', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    boardStoreState.boards = [
      makeBoard(),
      makeBoard({
        id: 2,
        name: 'School',
        description: 'Classroom activities',
      }),
    ];
    boardStoreState.assignedBoards = [];
    authState.user.user_type = 'admin';
  });

  it('keeps board loading client-side when the query changes', () => {
    renderCommunication();

    expect(boardStoreState.fetchBoards).toHaveBeenCalledWith(
      undefined,
      undefined,
      false,
      1,
    );

    fireEvent.change(screen.getByPlaceholderText('Search boards...'), {
      target: { value: 'nonsense' },
    });

    expect(boardStoreState.fetchBoards).toHaveBeenCalledTimes(1);
    expect(screen.getByText('No boards match your search')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search boards...'), {
      target: { value: '' },
    });

    expect(screen.getByText('Morning Routine')).toBeInTheDocument();
    expect(screen.getByText('School')).toBeInTheDocument();
  });

  it('keeps boards visible when only their description matches', () => {
    renderCommunication();

    fireEvent.change(screen.getByPlaceholderText('Search boards...'), {
      target: { value: 'classroom' },
    });

    expect(screen.getByText('School')).toBeInTheDocument();
    expect(screen.queryByText('Morning Routine')).not.toBeInTheDocument();
    expect(screen.queryByText('No boards match your search')).not.toBeInTheDocument();
  });

  it.each(['teacher', 'student'] as const)(
    'shows the no-match state for a %s search',
    (userType) => {
      authState.user.user_type = userType;
      if (userType === 'student') {
        boardStoreState.boards = [];
        boardStoreState.assignedBoards = [
          makeBoard(),
          makeBoard({ id: 2, name: 'School', description: 'Classroom activities' }),
        ];
      }

      renderCommunication();

      fireEvent.change(screen.getByPlaceholderText('Search boards...'), {
        target: { value: 'nonsense' },
      });

      expect(screen.getByText('No boards match your search')).toBeInTheDocument();
    },
  );

  it('uses role guidance only when there is no active query and no boards', () => {
    boardStoreState.boards = [];
    renderCommunication();

    expect(screen.getByText('No boards found')).toBeInTheDocument();
    expect(
      screen.getByText('Create a board in the Boards section first.'),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search boards...'), {
      target: { value: 'nonsense' },
    });

    expect(screen.getByText('No boards match your search')).toBeInTheDocument();
    expect(screen.queryByText('No boards found')).not.toBeInTheDocument();
  });
});
