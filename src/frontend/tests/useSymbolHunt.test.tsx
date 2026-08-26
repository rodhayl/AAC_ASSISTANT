import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSymbolHunt } from '../src/hooks/useSymbolHunt';
import type { Board, BoardSymbol } from '../src/types';

const getApi = vi.hoisted(() => vi.fn());
const postApi = vi.hoisted(() => vi.fn());
const enqueue = vi.hoisted(() => vi.fn());
const cancelAll = vi.hoisted(() => vi.fn());

vi.mock('../src/lib/api', () => ({
  default: { get: getApi, post: postApi },
}));

vi.mock('../src/lib/tts', () => ({
  tts: { enqueue, cancelAll },
}));

const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    username: 'admin1',
    user_type: 'admin',
    settings: { voice_mode_enabled: true },
  },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) =>
      (globalThis as typeof globalThis & {
        __aacTestTranslation?: (namespace: string, key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) => string;
      }).__aacTestTranslation?.('games', key, arg2, arg3) ?? key,
  }),
}));

function makeSymbol(id: number, label: string): BoardSymbol {
  return {
    id,
    symbol_id: id,
    position_x: 0,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: { id, label, category: 'core' },
  };
}

function makeBoard(id: number, name: string, symbols: BoardSymbol[]): Board {
  return {
    id,
    name,
    playable_symbols_count: symbols.length,
    symbols,
  } as Board;
}

const addToast = vi.fn();

// Flush pending microtasks (promise-only) without advancing fake timers.
const flushMicrotasks = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

describe('useSymbolHunt game logic', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getApi.mockResolvedValue({ data: [] });
    postApi.mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('loads playable boards and partitions unplayable ones', async () => {
    getApi.mockResolvedValue({
      data: [
        makeBoard(1, 'Playable', [makeSymbol(1, 'A'), makeSymbol(2, 'B')]),
        makeBoard(2, 'Locked', [makeSymbol(3, 'Only')]),
      ],
    });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.playableBoards.map((b) => b.name)).toEqual(['Playable']);
    expect(result.current.unplayableBoards.map((b) => b.name)).toEqual(['Locked']);
  });

  it('keeps duplicate-label boards unplayable even when placements >= 2', async () => {
    // Two playable placements with the same normalized label: the list must
    // not offer this board as playable, because startGame would reject it.
    getApi.mockResolvedValue({
      data: [
        makeBoard(1, 'Dupe', [makeSymbol(1, 'Apple'), makeSymbol(2, 'apple')]),
        makeBoard(2, 'Real', [makeSymbol(3, 'Apple'), makeSymbol(4, 'Banana')]),
      ],
    });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.playableBoards.map((b) => b.name)).toEqual(['Real']);
    expect(result.current.unplayableBoards.map((b) => b.name)).toEqual(['Dupe']);
  });

  it('starts a game with deduplicated symbols, round 1 and score 0', async () => {
    getApi
      .mockResolvedValueOnce({ data: [makeBoard(1, 'Board', [makeSymbol(1, 'A'), makeSymbol(2, 'B')])] })
      .mockResolvedValueOnce({
        data: makeBoard(1, 'Board', [makeSymbol(1, 'Dog'), makeSymbol(2, 'Cat'), makeSymbol(3, 'dog')]),
      });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.startGame(result.current.playableBoards[0]);
    });

    expect(result.current.gameState).toBe('playing');
    expect(result.current.round).toBe(1);
    expect(result.current.score).toBe(0);
    // "Dog" and "dog" normalize to one unique label.
    expect(result.current.symbols).toHaveLength(2);
    expect(result.current.targetSymbol).not.toBeNull();
  });

  it('rejects a board with fewer than two unique symbols', async () => {
    getApi
      .mockResolvedValueOnce({ data: [makeBoard(1, 'Board', [makeSymbol(1, 'A'), makeSymbol(2, 'B')])] })
      .mockResolvedValueOnce({
        data: makeBoard(1, 'Board', [makeSymbol(1, 'Same'), makeSymbol(2, 'same')]),
      });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.startGame(result.current.playableBoards[0]);
    });

    expect(result.current.gameState).toBe('selecting');
    expect(addToast).toHaveBeenCalledWith('This board needs at least 2 symbols to play.', 'error');
  });

  it('shows an error toast when the board fails to load', async () => {
    getApi
      .mockResolvedValueOnce({ data: [makeBoard(1, 'Board', [makeSymbol(1, 'A'), makeSymbol(2, 'B')])] })
      .mockRejectedValueOnce(new Error('offline'));

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { result } = renderHook(() => useSymbolHunt({ addToast }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.startGame(result.current.playableBoards[0]);
    });

    expect(result.current.gameState).toBe('selecting');
    expect(addToast).toHaveBeenCalledWith(expect.stringContaining('load'), 'error');
    consoleSpy.mockRestore();
  });

  it('increments score and advances the round on a correct answer', async () => {
    vi.useFakeTimers();
    getApi
      .mockResolvedValueOnce({ data: [makeBoard(1, 'Board', [makeSymbol(1, 'A'), makeSymbol(2, 'B')])] })
      .mockResolvedValueOnce({
        data: makeBoard(1, 'Board', [makeSymbol(1, 'Dog'), makeSymbol(2, 'Cat')]),
      });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));
    await flushMicrotasks();
    expect(result.current.loading).toBe(false);

    await act(async () => {
      await result.current.startGame(result.current.playableBoards[0]);
    });

    const target = result.current.targetSymbol!;
    act(() => result.current.handleSymbolClick(target));

    expect(result.current.feedback).toBe('correct');
    expect(result.current.score).toBe(1);

    act(() => vi.advanceTimersByTime(1500));
    expect(result.current.round).toBe(2);
    expect(result.current.feedback).toBeNull();
  });

  it('marks an incorrect answer without scoring and resets feedback', async () => {
    vi.useFakeTimers();
    getApi
      .mockResolvedValueOnce({ data: [makeBoard(1, 'Board', [makeSymbol(1, 'A'), makeSymbol(2, 'B')])] })
      .mockResolvedValueOnce({
        data: makeBoard(1, 'Board', [makeSymbol(1, 'Dog'), makeSymbol(2, 'Cat')]),
      });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));
    await flushMicrotasks();
    expect(result.current.loading).toBe(false);

    await act(async () => {
      await result.current.startGame(result.current.playableBoards[0]);
    });

    const target = result.current.targetSymbol!;
    const wrong = result.current.symbols.find((s) => s.id !== target.id)!;
    act(() => result.current.handleSymbolClick(wrong));

    expect(result.current.feedback).toBe('incorrect');
    expect(result.current.incorrectSymbolId).toBe(wrong.id);
    expect(result.current.score).toBe(0);

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.feedback).toBeNull();
    expect(result.current.incorrectSymbolId).toBeNull();
    expect(result.current.round).toBe(1);
  });

  it('finishes the game after ten correct rounds', async () => {
    vi.useFakeTimers();
    getApi
      .mockResolvedValueOnce({ data: [makeBoard(1, 'Board', [makeSymbol(1, 'A'), makeSymbol(2, 'B')])] })
      .mockResolvedValueOnce({
        data: makeBoard(1, 'Board', [makeSymbol(1, 'Dog'), makeSymbol(2, 'Cat')]),
      });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));
    await flushMicrotasks();
    expect(result.current.loading).toBe(false);

    await act(async () => {
      await result.current.startGame(result.current.playableBoards[0]);
    });

    for (let round = 1; round <= 10; round++) {
      const target = result.current.targetSymbol!;
      act(() => result.current.handleSymbolClick(target));
      act(() => vi.advanceTimersByTime(1500));
    }

    expect(result.current.score).toBe(10);
    expect(result.current.gameState).toBe('finished');
  });

  it('playAgain resets the score and round without leaving the game', async () => {
    vi.useFakeTimers();
    getApi
      .mockResolvedValueOnce({ data: [makeBoard(1, 'Board', [makeSymbol(1, 'A'), makeSymbol(2, 'B')])] })
      .mockResolvedValueOnce({
        data: makeBoard(1, 'Board', [makeSymbol(1, 'Dog'), makeSymbol(2, 'Cat')]),
      });

    const { result } = renderHook(() => useSymbolHunt({ addToast }));
    await flushMicrotasks();
    expect(result.current.loading).toBe(false);

    await act(async () => {
      await result.current.startGame(result.current.playableBoards[0]);
    });

    act(() => result.current.handleSymbolClick(result.current.targetSymbol!));
    act(() => vi.advanceTimersByTime(1500));
    expect(result.current.score).toBe(1);

    act(() => result.current.playAgain());
    expect(result.current.gameState).toBe('playing');
    expect(result.current.round).toBe(1);
    expect(result.current.score).toBe(0);
  });
});
