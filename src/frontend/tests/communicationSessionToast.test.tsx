import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Communication } from '../src/pages/Communication';
import { useLearningStore } from '../src/store/learningStore';

const addToast = vi.hoisted(() => vi.fn());
const board = vi.hoisted(() => ({
  id: 7,
  name: 'Practice Board',
  description: 'A board for practice',
  grid_rows: 4,
  grid_cols: 5,
  playable_symbols_count: 20,
  symbols: [],
}));

vi.mock('../src/store/authStore', () => {
  const state = {
    user: {
      id: 1,
      user_type: 'teacher',
      display_name: 'Teacher',
      username: 'teacher',
      settings: { voice_mode_enabled: false },
    },
  };
  const useAuthStore = Object.assign(() => state, {
    getState: () => state,
  });
  return { useAuthStore };
});

vi.mock('../src/store/boardStore', () => {
  const state = {
    boards: [board],
    assignedBoards: [],
    currentBoard: board,
    isLoading: false,
    hasMore: false,
    page: 1,
    fetchBoard: vi.fn(),
    fetchBoards: vi.fn(),
    fetchAssignedBoards: vi.fn(),
  };
  const useBoardStore = () => state;
  return { useBoardStore };
});

vi.mock('../src/store/toastStore', () => ({
  useToastStore: () => ({ addToast }),
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

vi.mock('../src/components/learning/BoardsAndTopicsSidebar', () => ({
  BoardsAndTopicsSidebar: ({
    onStartActivity,
  }: {
    onStartActivity: (topic: string, purpose: string) => void;
  }) => (
    <button onClick={() => onStartActivity('general', 'practice')}>
      Start activity
    </button>
  ),
}));

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

const getApi = async () => (await import('../src/lib/api')).default as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

describe('communication session start feedback', () => {
  beforeEach(async () => {
    const api = await getApi();
    api.get.mockReset();
    api.post.mockReset();
    api.post.mockResolvedValue({
      data: { success: false, error: 'server refused' },
    });
    addToast.mockReset();

    useLearningStore.setState({
      currentSession: null,
      currentQuestion: null,
      lastAnswer: null,
      isLoading: false,
      error: null,
      messages: [],
    });
  });

  it('rejects failed API responses so the error toast replaces success', async () => {
    render(<Communication />);
    fireEvent.click(screen.getByRole('button', { name: /Practice Board/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Start activity' }));

    await waitFor(() => {
      expect(addToast).toHaveBeenCalledWith('Failed to start session', 'error');
    });
    expect(addToast).not.toHaveBeenCalledWith('Session started', 'success');
    expect(useLearningStore.getState().error).toBe('server refused');
  });

  it('preserves the server failure message and rejection for direct callers', async () => {
    await expect(
      useLearningStore.getState().startSession(
        { topic: 'general', purpose: 'practice', difficulty: 'basic' },
        1,
      ),
    ).rejects.toThrow('server refused');
    expect(useLearningStore.getState().error).toBe('server refused');
  });
});
