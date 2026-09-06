import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useLearningStore } from '../src/store/learningStore';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('../src/lib/tts', () => ({
  tts: { cancelAll: vi.fn() },
}));

vi.mock('../src/store/authStore', () => {
  const state = { user: { id: 1, user_type: 'student' } };
  const useAuthStore = Object.assign(
    (selector?: (value: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useAuthStore };
});

vi.mock('../src/i18n/index', () => ({
  default: { t: (key: string) => key, language: 'en' },
}));

const getApi = async () => (await import('../src/lib/api')).default as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

const startedSession = {
  success: true,
  session_id: 7,
  topic: 'Weather',
  welcome_message: 'Welcome!',
};

// Reset mocks and the module-level store between tests: the start/end success
// paths fire unawaited follow-up work (history refresh) that would otherwise
// leak into the next test.
beforeEach(async () => {
  const api = await getApi();
  api.get.mockReset();
  api.post.mockReset();
  useLearningStore.setState({
    currentSession: null,
    currentQuestion: null,
    lastAnswer: null,
    revealedAnswer: null,
    progressStats: null,
    lastSessionSummary: null,
    isLoading: false,
    error: null,
    messages: [],
    sessionHistory: [],
    isLoadingHistory: false,
  });
});

describe('learning store double-request guards', () => {
  beforeEach(async () => {
    const api = await getApi();
    api.get.mockResolvedValue({ data: { sessions: [] } });
  });

  it('drops the second concurrent start instead of creating two sessions', async () => {
    const api = await getApi();
    let releaseFirst: (() => void) | undefined;
    api.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseFirst = () =>
            resolve({ data: { ...startedSession, session_id: 7 } });
        }),
    );

    const first = useLearningStore.getState().startSession(
      { topic: 'Weather', purpose: 'practice' } as never,
      1,
    );
    // The double click arrives while the first start is still in flight.
    await useLearningStore.getState().startSession(
      { topic: 'Weather', purpose: 'practice' } as never,
      1,
    );
    releaseFirst?.();
    await first;
    await vi.waitFor(() => {
      expect(useLearningStore.getState().currentSession?.session_id).toBe(7);
    });
    await vi.waitFor(async () => {
      // The start success path fires an unawaited history refresh; settle it
      // so its request cannot land in a later assertion window.
      await Promise.resolve();
      expect(
        api.post.mock.calls.filter(([url]) => url === '/learning/start'),
      ).toHaveLength(1);
    });
  });

  it('drops the second concurrent end instead of double-spending the summary', async () => {
    const api = await getApi();
    let releaseEnd: (() => void) | undefined;
    api.post.mockImplementationOnce((url: string) => {
      expect(url).toBe('/learning/7/end');
      return new Promise((resolve) => {
        releaseEnd = () => resolve({ data: { success: true, summary: 'Nice work' } });
      });
    });

    useLearningStore.setState({
      currentSession: { session_id: 7 } as never,
      isLoading: false,
    });

    // One click already put the end request in flight (isLoading true).
    const inFlight = useLearningStore.getState().endSession(7);
    // The double click must be dropped while the first end is in flight.
    await useLearningStore.getState().endSession(7);
    releaseEnd?.();
    await inFlight;
    await vi.waitFor(async () => {
      // Settle the success path's unawaited history refresh before counting.
      await Promise.resolve();
      expect(
        api.post.mock.calls.filter(([url]) => url === '/learning/7/end'),
      ).toHaveLength(1);
    });
    expect(useLearningStore.getState().currentSession).toBeNull();
  });
});

describe('learning store per-operation guards', () => {
  beforeEach(async () => {
    const api = await getApi();
    api.get.mockResolvedValue({ data: { sessions: [] } });
  });

  it('ends the session while a question generation is still in flight', async () => {
    const api = await getApi();
    useLearningStore.setState({
      currentSession: { session_id: 7 } as never,
      // A question generation is in flight (shared chat spinner on).
      isLoading: true,
      isAskingQuestion: true,
      isEndingSession: false,
    });
    api.post.mockResolvedValueOnce({ data: { success: true, summary: 'Done' } });

    await useLearningStore.getState().endSession(7);

    expect(
      api.post.mock.calls.filter(([url]) => url === '/learning/7/end'),
    ).toHaveLength(1);
    expect(useLearningStore.getState().currentSession).toBeNull();
  });

  it('starts a session while an unrelated answer submit is still in flight', async () => {
    const api = await getApi();
    useLearningStore.setState({
      currentSession: null,
      isLoading: true,
      isSubmittingAnswer: true,
      isStartingSession: false,
    });
    api.post.mockImplementation((url: string) => {
      if (url === '/learning/start') {
        return Promise.resolve({ data: { ...startedSession, session_id: 9 } });
      }
      return Promise.resolve({ data: {} });
    });

    await useLearningStore
      .getState()
      .startSession({ topic: 'Weather', purpose: 'practice' } as never, 1);

    expect(
      api.post.mock.calls.filter(([url]) => url === '/learning/start'),
    ).toHaveLength(1);
    expect(useLearningStore.getState().currentSession?.session_id).toBe(9);
  });
});

describe('learning store history walk', () => {
  it('walks every history page instead of silently truncating', async () => {
    const api = await getApi();
    const page = (index: number) =>
      Array.from({ length: 1000 }, (_, i) => ({
        id: index * 1000 + i + 1,
        topic: `Session ${index * 1000 + i + 1}`,
        purpose: 'practice',
        status: 'completed',
        created_at: '2026-08-04T10:00:00Z',
      }));
    api.get.mockImplementation((_url: string, config?: { params?: { skip?: number } }) => {
      const skip = config?.params?.skip ?? 0;
      if (skip === 0) return Promise.resolve({ data: { sessions: page(0) } });
      if (skip === 1000) return Promise.resolve({ data: { sessions: page(1) } });
      return Promise.resolve({ data: { sessions: [page(2)[0]] } });
    });

    await useLearningStore.getState().fetchSessionHistory(1);

    const historyCalls = api.get.mock.calls.filter(
      ([url]) => url === '/learning/history/1',
    );
    expect(historyCalls).toHaveLength(3);
    expect(historyCalls[1][1]).toMatchObject({ params: { skip: 1000, limit: 1000 } });
    expect(useLearningStore.getState().sessionHistory).toHaveLength(2001);
  });
});
