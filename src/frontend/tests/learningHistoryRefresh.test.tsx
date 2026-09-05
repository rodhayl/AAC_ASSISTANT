import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Learning } from '../src/pages/Learning';
import { useLearningStore } from '../src/store/learningStore';

vi.mock('../src/store/authStore', () => {
  const state = {
    user: {
      id: 1,
      user_type: 'teacher',
      display_name: 'Teacher',
      settings: { voice_mode_enabled: false },
    },
  };
  const useAuthStore = Object.assign(
    (selector?: (value: typeof state) => unknown) => selector ? selector(state) : state,
    { getState: () => state },
  );
  return { useAuthStore };
});

vi.mock('../src/store/boardStore', () => {
  const fetchBoards = vi.fn();
  const state = {
    fetchBoards,
    boards: [],
    assignedBoards: [],
  };
  const useBoardStore = (selector?: (value: typeof state) => unknown) =>
    selector ? selector(state) : state;
  return { useBoardStore };
});

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

const getApi = async () => (await import('../src/lib/api')).default as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};
let historyApi: Awaited<ReturnType<typeof getApi>>;

describe('Learning history refresh', () => {
  beforeEach(async () => {
    const api = await getApi();
    historyApi = api;
    api.get.mockReset();
    api.post.mockReset();
    api.post.mockResolvedValue({ data: [] });

    const history = {
      id: 42,
      topic: 'Fresh session',
      created_at: '2026-08-04T10:00:00Z',
      status: 'in_progress',
      comprehension_score: 0.75,
    };
    useLearningStore.setState({
      currentSession: null,
      currentQuestion: null,
      lastAnswer: null,
      isLoading: false,
      error: null,
      messages: [],
      sessionHistory: [],
      isLoadingHistory: false,
    });

    // The second history request represents the server returning a session
    // created after the initial page mount.
    let historyRequestCount = 0;
    api.get.mockImplementation((url: string) => {
      if (url === '/learning/history/1') {
        historyRequestCount += 1;
        return Promise.resolve({
          data: { sessions: historyRequestCount === 1 ? [] : [history] },
        });
      }
      if (url === '/learning-modes/') {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: [] });
    });
  });

  it('refetches and renders sessions when Show History opens', async () => {
    render(<Learning />);

    await waitFor(() => {
      expect(historyApi.get.mock.calls.filter(([url]) => url === '/learning/history/1')).toHaveLength(1);
    });
    expect(screen.queryByText('Fresh session')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('showHistory'));

    await waitFor(() => {
      expect(historyApi.get.mock.calls.filter(([url]) => url === '/learning/history/1')).toHaveLength(2);
      expect(screen.getByText('Fresh session')).toBeInTheDocument();
      expect(screen.getByText('score 75%')).toBeInTheDocument();
    });
  });
});
