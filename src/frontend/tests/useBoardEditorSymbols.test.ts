import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useBoardEditorSymbols } from '../src/hooks/useBoardEditorSymbols';
import type { Board, BoardSymbol } from '../src/types';

function makeSymbol(id: number, label: string, x = 0, y = 0): BoardSymbol {
  return {
    id,
    symbol_id: id,
    position_x: x,
    position_y: y,
    size: 1,
    is_visible: true,
    symbol: {
      id,
      label,
      category: 'general',
      language: 'en',
      is_builtin: true,
      created_at: '2026-01-01T00:00:00Z',
    },
  };
}

function makeBoard(id: number, symbol: BoardSymbol): Board {
  return {
    id,
    user_id: 1,
    name: `Board ${id}`,
    category: 'general',
    is_public: false,
    is_template: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    grid_rows: 2,
    grid_cols: 2,
    symbols: [symbol],
  };
}

describe('useBoardEditorSymbols context isolation', () => {
  it('does not carry dirty state or overrides into another board or user', () => {
    const firstBoard = makeBoard(1, makeSymbol(1, 'Apple'));
    const secondBoard = makeBoard(2, makeSymbol(2, 'Banana'));
    const sendMove = vi.fn();
    const { result, rerender } = renderHook(
      ({ board, userId }: { board: Board | null; userId: number }) =>
        useBoardEditorSymbols({ currentBoard: board, userId }),
      { initialProps: { board: firstBoard, userId: 1 } },
    );

    act(() => {
      result.current.handleDragEnd(1, { x: 1, y: 1 }, sendMove);
    });
    expect(result.current.hasChanges).toBe(true);
    expect(result.current.localSymbols[0]).toMatchObject({ position_x: 1, position_y: 1 });

    rerender({ board: secondBoard, userId: 1 });
    expect(result.current.hasChanges).toBe(false);
    expect(result.current.localSymbols[0]).toMatchObject({ id: 2, position_x: 0, position_y: 0 });

    rerender({ board: firstBoard, userId: 2 });
    expect(result.current.hasChanges).toBe(false);
    expect(result.current.localSymbols[0]).toMatchObject({ id: 1, position_x: 0, position_y: 0 });

    // Returning to the original account/board may recover its own local edit,
    // but neither context can observe the other context's pending change.
    rerender({ board: firstBoard, userId: 1 });
    expect(result.current.hasChanges).toBe(true);
    expect(result.current.localSymbols[0]).toMatchObject({ position_x: 1, position_y: 1 });
  });
});
