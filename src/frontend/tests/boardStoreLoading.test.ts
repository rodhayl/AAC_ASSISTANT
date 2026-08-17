import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  apiOffline: {
    isOffline: () => false,
  },
  extractError: (_error: unknown, fallback: string) => fallback,
}));

import api from '../src/lib/api';
import { useBoardStore } from '../src/store/boardStore';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('board store loading state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBoardStore.setState({
      boards: [],
      assignedBoards: [],
      currentBoard: null,
      isLoading: false,
      isListLoading: false,
      isBoardLoading: false,
      error: null,
      lastFetchTime: null,
      assignedBoardsLastFetchTime: null,
      assignedBoardsStudentId: undefined,
      isFiltered: false,
      hasMore: true,
      page: 1,
      currentUserId: undefined,
      currentSearchQuery: '',
    });
  });

  it('does not let a completed list request clear board loading', async () => {
    const listRequest = deferred<{ data: Array<{ id: number }> }>();
    const boardRequest = deferred<{ data: { id: number; symbols: [] } }>();
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/boards/') return listRequest.promise as never;
      if (url === '/boards/1') return boardRequest.promise as never;
      throw new Error(`Unexpected URL: ${url}`);
    });

    const listPromise = useBoardStore.getState().fetchBoards();
    const boardPromise = useBoardStore.getState().fetchBoard(1);

    expect(useBoardStore.getState()).toMatchObject({
      isListLoading: true,
      isBoardLoading: true,
    });

    listRequest.resolve({ data: [{ id: 1 }] });
    await listPromise;

    expect(useBoardStore.getState()).toMatchObject({
      isListLoading: false,
      isBoardLoading: true,
    });

    boardRequest.resolve({ data: { id: 1, symbols: [] } });
    await boardPromise;

    expect(useBoardStore.getState()).toMatchObject({
      isListLoading: false,
      isBoardLoading: false,
      currentBoard: { id: 1, symbols: [] },
    });
  });

  it('ignores a stale board-list response after a newer search completes', async () => {
    const firstListRequest = deferred<{ data: Array<{ id: number }> }>();
    const secondListRequest = deferred<{ data: Array<{ id: number }> }>();
    vi.mocked(api.get).mockImplementation((_url, config) => {
      const name = (config?.params as { name?: string } | undefined)?.name;
      if (name === 'old') return firstListRequest.promise as never;
      if (name === 'new') return secondListRequest.promise as never;
      throw new Error(`Unexpected request: ${name}`);
    });

    const firstPromise = useBoardStore.getState().fetchBoards(undefined, 'old');
    const secondPromise = useBoardStore.getState().fetchBoards(undefined, 'new');

    secondListRequest.resolve({ data: [{ id: 2 }] });
    await secondPromise;
    expect(useBoardStore.getState().boards).toEqual([{ id: 2 }]);

    firstListRequest.resolve({ data: [{ id: 1 }] });
    await firstPromise;
    expect(useBoardStore.getState().boards).toEqual([{ id: 2 }]);
    expect(useBoardStore.getState().isListLoading).toBe(false);
  });

  it('caches board results for the same user but not a different user', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [{ id: 1 }] } as never);

    await useBoardStore.getState().fetchBoards(10);
    await useBoardStore.getState().fetchBoards(10);
    await useBoardStore.getState().fetchBoards(11);

    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.get).toHaveBeenLastCalledWith('/boards/', {
      params: { user_id: 11, skip: 0, limit: 100 },
    });
  });

  it('does not cache filtered, paginated, or forced board requests', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [{ id: 1 }] } as never);

    await useBoardStore.getState().fetchBoards(10);
    await useBoardStore.getState().fetchBoards(10, 'daily');
    await useBoardStore.getState().fetchBoards(10, undefined, false, 2);
    await useBoardStore.getState().fetchBoards(10, undefined, true, 1);

    expect(api.get).toHaveBeenCalledTimes(4);
  });

  it('does not reuse assigned-board results for a different student', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [{ id: 1 }] } as never);

    await useBoardStore.getState().fetchAssignedBoards(10);
    await useBoardStore.getState().fetchAssignedBoards(11);

    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.get).toHaveBeenLastCalledWith('/boards/assigned', {
      params: { student_id: 11 },
    });
  });

  it('invalidates the assigned-board cache after assignment', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [{ id: 1 }] } as never);
    vi.mocked(api.post).mockResolvedValue({ data: { ok: true } } as never);

    await useBoardStore.getState().fetchAssignedBoards(10);
    expect(useBoardStore.getState().assignedBoardsLastFetchTime).not.toBeNull();

    await useBoardStore.getState().assignBoardToStudent(2, 10);
    expect(useBoardStore.getState().assignedBoardsLastFetchTime).toBeNull();
    await useBoardStore.getState().fetchAssignedBoards(10);

    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('ignores a stale board response after navigation changes the requested board', async () => {
    const firstBoardRequest = deferred<{ data: { id: number; symbols: [] } }>();
    const secondBoardRequest = deferred<{ data: { id: number; symbols: [] } }>();
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/boards/1') return firstBoardRequest.promise as never;
      if (url === '/boards/2') return secondBoardRequest.promise as never;
      throw new Error(`Unexpected URL: ${url}`);
    });

    const firstPromise = useBoardStore.getState().fetchBoard(1);
    const secondPromise = useBoardStore.getState().fetchBoard(2);

    secondBoardRequest.resolve({ data: { id: 2, symbols: [] } });
    await secondPromise;
    expect(useBoardStore.getState()).toMatchObject({
      currentBoard: { id: 2 },
      isBoardLoading: false,
    });

    firstBoardRequest.resolve({ data: { id: 1, symbols: [] } });
    await firstPromise;
    expect(useBoardStore.getState().currentBoard).toMatchObject({ id: 2 });
  });
});
