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
  extractError: (error: { message?: string } | undefined, fallback: string) =>
    error?.message || fallback,
}));

import api from '../src/lib/api';
import i18n from '../src/i18n/index';
import { useBoardStore } from '../src/store/boardStore';
import { useNotificationsStore } from '../src/store/notificationsStore';

const board = {
  id: 1,
  user_id: 7,
  name: 'My Board',
  description: 'desc',
  category: 'general',
  is_public: false,
  is_template: false,
  grid_rows: 4,
  grid_cols: 5,
  symbols: [],
};

describe('board store CRUD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNotificationsStore.setState({ items: [] });
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
      currentUserId: 7,
      currentSearchQuery: '',
    });
  });

  it('creates a board and refreshes the list', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: board });
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [board] });

    await useBoardStore.getState().createBoard({ name: 'My Board' }, 7);

    expect(api.post).toHaveBeenCalledWith(
      '/boards/',
      { name: 'My Board' },
      { params: { user_id: 7 } },
    );
    expect(useBoardStore.getState().boards).toEqual([board]);
    expect(useBoardStore.getState().error).toBeNull();
  });

  it('records an error and rethrows when board creation fails', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('offline'));

    await expect(
      useBoardStore.getState().createBoard({ name: 'X' }, 7),
    ).rejects.toThrow('offline');
    expect(useBoardStore.getState().error).toBe('offline');
  });

  it('updates the board in both the list and the current board', async () => {
    const updated = { ...board, name: 'Renamed' };
    useBoardStore.setState({ boards: [board], currentBoard: board });
    (api.put as ReturnType<typeof vi.fn>).mockResolvedValue({ data: updated });

    await useBoardStore.getState().updateBoard(1, { name: 'Renamed' });

    expect(useBoardStore.getState().boards[0].name).toBe('Renamed');
    expect(useBoardStore.getState().currentBoard?.name).toBe('Renamed');
  });

  it('deletes a board locally when skipRefresh is set', async () => {
    useBoardStore.setState({ boards: [board], currentBoard: board });
    (api.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});

    await useBoardStore.getState().deleteBoard(1, true);

    expect(useBoardStore.getState().boards).toEqual([]);
    expect(useBoardStore.getState().currentBoard).toBeNull();
  });

  it('duplicates a board including its symbols', async () => {
    const source = {
      ...board,
      symbols: [
        {
          symbol: { id: 10 },
          position_x: 0,
          position_y: 1,
          size: 1,
          is_visible: true,
          custom_text: 'Hi',
        },
      ],
    };
    const copySuffix = i18n.t('boards:copySuffix', ' (Copy)');
    const copy = { ...board, id: 2, name: `My Board${copySuffix}` };
    (api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: source }) // base board lookup
      .mockResolvedValueOnce({ data: [copy] }); // list refresh
    (api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: copy }) // board creation
      .mockResolvedValueOnce({}); // symbol copy

    await useBoardStore.getState().duplicateBoard(1, 7);

    expect(api.post).toHaveBeenCalledWith(
      '/boards/',
      expect.objectContaining({ name: `My Board${copySuffix}` }),
      { params: { user_id: 7 } },
    );
    expect(api.post).toHaveBeenCalledWith(
      '/boards/2/symbols',
      expect.objectContaining({ symbol_id: 10, position_x: 0, position_y: 1 }),
    );
  });

  it('drops links to boards the new owner cannot view instead of failing mid-copy', async () => {
    const source = {
      ...board,
      symbols: [
        {
          id: 100,
          symbol: { id: 10 },
          position_x: 0,
          position_y: 0,
          size: 1,
          is_visible: true,
          linked_board_id: 99, // private board of the original owner
        },
        {
          id: 101,
          symbol: { id: 11 },
          position_x: 1,
          position_y: 0,
          size: 1,
          is_visible: true,
          linked_board_id: 12, // accessible linked board
        },
      ],
    };
    const copy = { ...board, id: 2, name: 'My Board (Copy)' };
    (api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: source }) // base board lookup
      .mockRejectedValueOnce(new Error('403')) // linked board 99 is inaccessible
      .mockResolvedValueOnce({ data: { id: 12 } }) // linked board 12 resolves
      .mockResolvedValueOnce({ data: [copy] }); // list refresh
    (api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: copy }) // board creation
      .mockResolvedValueOnce({}) // symbol 10
      .mockResolvedValueOnce({}); // symbol 11

    await useBoardStore.getState().duplicateBoard(1, 7);

    // Symbol with an inaccessible link is copied without the link; the
    // accessible one keeps it. The copy completes despite the 403 on one link.
    expect(api.post).toHaveBeenCalledWith(
      '/boards/2/symbols',
      expect.objectContaining({ symbol_id: 10, linked_board_id: null }),
    );
    expect(api.post).toHaveBeenCalledWith(
      '/boards/2/symbols',
      expect.objectContaining({ symbol_id: 11, linked_board_id: 12 }),
    );
    expect(api.get).toHaveBeenCalledWith('/boards/99', {
      params: { skip_translation: true },
    });
  });

  it('adds a symbol to the current board when it is the modified board', async () => {
    const boardSymbol = { id: 55, symbol_id: 10, position_x: 2, position_y: 2 };
    useBoardStore.setState({ currentBoard: board });
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: boardSymbol });

    const result = await useBoardStore
      .getState()
      .addSymbolToBoard(1, 10, { x: 2, y: 2 });

    expect(result).toEqual(boardSymbol);
    expect(useBoardStore.getState().currentBoard?.symbols).toEqual([boardSymbol]);
  });

  it('removes a symbol from the current board', async () => {
    useBoardStore.setState({
      currentBoard: {
        ...board,
        symbols: [{ id: 55 }, { id: 56 }],
      },
    });
    (api.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});

    await useBoardStore.getState().deleteBoardSymbol(1, 55);

    expect(useBoardStore.getState().currentBoard?.symbols).toEqual([{ id: 56 }]);
  });

  it('rethrows symbol deletion failures with a stable error', async () => {
    (api.delete as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('gone'));

    await expect(
      useBoardStore.getState().deleteBoardSymbol(1, 55),
    ).rejects.toThrow('gone');
    expect(useBoardStore.getState().error).toBe('gone');
  });

  it('batch-updates symbols and refreshes the board', async () => {
    (api.put as ReturnType<typeof vi.fn>).mockResolvedValue({});
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: board });

    await useBoardStore.getState().batchUpdateSymbols(1, [{ id: 55, position_x: 3 }]);

    expect(api.put).toHaveBeenCalledWith(
      '/boards/1/symbols/batch',
      [{ id: 55, position_x: 3 }],
    );
    expect(useBoardStore.getState().currentBoard).toEqual(board);
  });

  it('assigns a board to a student and invalidates the cached list', async () => {
    useBoardStore.setState({ assignedBoardsStudentId: 3, assignedBoardsLastFetchTime: 123 });
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({});

    await useBoardStore.getState().assignBoardToStudent(1, 3, 7);

    expect(api.post).toHaveBeenCalledWith('/boards/1/assign', {
      student_id: 3,
      assigned_by: 7,
    });
    expect(useBoardStore.getState().assignedBoardsLastFetchTime).toBeNull();
    expect(useNotificationsStore.getState().items.length).toBe(1);
  });

  it('records an error when the assignment fails', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('no roster'));

    await expect(
      useBoardStore.getState().assignBoardToStudent(1, 3),
    ).rejects.toThrow('no roster');
    expect(useBoardStore.getState().error).toBe('no roster');
  });
});
