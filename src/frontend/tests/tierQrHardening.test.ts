/**
 * PROMPT_5 Tiers Q/R — frontend hardening (store/lib layer).
 *
 * Each spec pins a defect that was reproducible before the fix:
 *  - H38/H59 a failed symbol send rethrew so the utterance is not discarded;
 *  - H44/H65 notification read-state is rolled back when the sync fails;
 *  - H57 a failed duplicate removes the half-copied board;
 *  - H63 topic pictograms match whole tokens ("ir" must not match "mirar");
 *  - H62 a board-less legacy saved topic cannot block the migration queue.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../src/lib/api', () => {
  const api = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  };
  return {
    default: api,
    apiOffline: { isOffline: vi.fn(() => false) },
    extractError: (error: unknown, fallback: string) =>
      error instanceof Error ? error.message : fallback,
  };
});

vi.mock('../src/lib/tts', () => ({
  tts: { cancelAll: vi.fn(), enqueue: vi.fn() },
}));

vi.mock('../src/i18n/index', () => ({
  default: {
    t: (key: string) => key,
    language: 'en',
    changeLanguage: vi.fn(),
  },
}));

vi.mock('../src/store/authStore', () => {
  const state = { user: { id: 1, user_type: 'student' } };
  const useAuthStore = Object.assign(
    (selector?: (value: typeof state) => unknown) => (selector ? selector(state) : state),
    { getState: () => state },
  );
  return { useAuthStore };
});

const getApi = async () =>
  (await import('../src/lib/api')).default as unknown as {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    put: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };

beforeEach(async () => {
  vi.clearAllMocks();
  const api = await getApi();
  api.get.mockReset();
  api.post.mockReset();
  api.put.mockReset();
  api.delete.mockReset();
  localStorage.clear();
});

describe('H38/H59 — failed symbol sends keep the composed utterance', () => {
  it('rethrows so callers can preserve the draft', async () => {
    const api = await getApi();
    const { useLearningStore } = await import('../src/store/learningStore');
    useLearningStore.setState({
      currentSession: { session_id: 7, topic: 'Weather' } as never,
      isLoading: false,
      isSubmittingAnswer: false,
      error: null,
    });
    api.post.mockRejectedValueOnce(new Error('network down'));

    await expect(
      useLearningStore
        .getState()
        .submitSymbolAnswer(7, [{ id: 1, label: 'agua' }]),
    ).rejects.toThrow('network down');
    expect(useLearningStore.getState().error).toBe('network down');
  });

  it('resolves on success', async () => {
    const api = await getApi();
    const { useLearningStore } = await import('../src/store/learningStore');
    useLearningStore.setState({
      currentSession: { session_id: 7, topic: 'Weather' } as never,
      isLoading: false,
      isSubmittingAnswer: false,
      error: null,
      messages: [],
    });
    api.post.mockResolvedValueOnce({
      data: {
        success: true,
        is_correct: true,
        feedback: 'Nice',
        response: 'Nice',
        correct_answer: 'agua',
      },
    });

    await expect(
      useLearningStore.getState().submitSymbolAnswer(7, [{ id: 1, label: 'agua' }]),
    ).resolves.toBeUndefined();
  });
});

describe('H44/H65 — notification read state rolls back on sync failure', () => {
  it('restores the unread flag when the PUT fails', async () => {
    const api = await getApi();
    const { useNotificationsStore } = await import('../src/store/notificationsStore');
    useNotificationsStore.setState({
      items: [
        { id: 5, title: 't', message: 'm', read: false, createdAt: Date.now() },
      ],
      loading: false,
      loaded: true,
    });
    api.put.mockRejectedValueOnce(new Error('offline'));

    await useNotificationsStore.getState().markAsRead(5);

    expect(useNotificationsStore.getState().items[0].read).toBe(false);
  });

  it('restores only the notifications it flipped for mark-all', async () => {
    const api = await getApi();
    const { useNotificationsStore } = await import('../src/store/notificationsStore');
    useNotificationsStore.setState({
      items: [
        { id: 5, title: 'a', message: 'm', read: true, createdAt: 1 },
        { id: 6, title: 'b', message: 'm', read: false, createdAt: 2 },
      ],
      loading: false,
      loaded: true,
    });
    api.put.mockRejectedValueOnce(new Error('offline'));

    await useNotificationsStore.getState().markAllAsRead();

    const byId = new Map(
      useNotificationsStore.getState().items.map((item) => [item.id, item.read]),
    );
    expect(byId.get(5)).toBe(true);
    expect(byId.get(6)).toBe(false);
  });
});

describe('H57 — a failed duplicate leaves no orphan board', () => {
  it('deletes the new board when copying a symbol fails', async () => {
    const api = await getApi();
    const { useBoardStore } = await import('../src/store/boardStore');
    useBoardStore.setState({
      boards: [],
      page: 1,
      isFiltered: false,
      currentUserId: undefined,
      currentSearchQuery: '',
      error: null,
      isLoading: false,
    });
    api.get.mockResolvedValueOnce({
      data: {
        id: 1,
        name: 'Original',
        user_id: 1,
        symbols: [
          {
            id: 11,
            symbol_id: 3,
            position_x: 0,
            position_y: 0,
            size: 1,
            is_visible: true,
            custom_text: null,
            color: null,
            linked_board_id: null,
          },
        ],
      },
    });
    api.post
      .mockResolvedValueOnce({ data: { id: 99, name: 'Original (copy)' } })
      .mockRejectedValueOnce(new Error('symbol copy failed'));
    api.delete.mockResolvedValue({ data: {} });

    await expect(
      useBoardStore.getState().duplicateBoard(1, 1),
    ).rejects.toThrow('symbol copy failed');

    expect(api.delete).toHaveBeenCalledWith('/boards/99');
  });
});

describe('H63 — topic pictograms match whole tokens', () => {
  it('does not match "ir" inside "mirar"', async () => {
    const { findTopicPictogram } = await import('../src/lib/topicCatalog');
    const symbols = [
      { id: 1, label: 'mirar', keywords: '', category: 'general', image_path: '/uploads/a.png' },
    ];

    const result = findTopicPictogram('travel', symbols, '✈️');

    expect(result.imagePath).toBeUndefined();
    expect(result.emoji).toBe('✈️');
  });

  it('still matches an exact token', async () => {
    const { findTopicPictogram } = await import('../src/lib/topicCatalog');
    const symbols = [
      { id: 1, label: 'ir', keywords: '', category: 'general', image_path: '/uploads/go.png' },
    ];

    const result = findTopicPictogram('travel', symbols, '✈️');

    expect(result.imagePath).toBe('/uploads/go.png');
  });
});

describe('H62 — a board-less legacy topic cannot block the migration', () => {
  it('drops unusable rows, posts only valid ones and clears the key', async () => {
    const api = await getApi();
    api.post.mockResolvedValue({ data: { success: true } });
    localStorage.setItem(
      'learning-topics-1',
      JSON.stringify([
        { id: 1, board: '', topic: 'no board', createdBy: 'me' },
        { id: 2, board: 'Comunicación', topic: 'valid', createdBy: 'me' },
      ]),
    );

    const { migrateLocalTopicsToBackend } = await import('../src/lib/learningTopics');
    await migrateLocalTopicsToBackend(1);

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post.mock.calls[0][1]).toMatchObject({ board: 'Comunicación' });
    expect(localStorage.getItem('learning-topics-1')).toBeNull();
  });
});
