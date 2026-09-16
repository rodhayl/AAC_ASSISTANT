import type { BoardSymbol } from '../types';

export const ARROW_DELTAS: Record<string, { dx: number; dy: number }> = {
  ArrowRight: { dx: 1, dy: 0 },
  ArrowLeft: { dx: -1, dy: 0 },
  ArrowDown: { dx: 0, dy: 1 },
  ArrowUp: { dx: 0, dy: -1 },
};

/**
 * Next occupied cell walking in the arrow direction from `currentIndex`,
 * skipping empty cells so keyboard navigation jumps between real symbols;
 * `null` when the edge of the grid is reached first. Used by the
 * Communication grid's arrow-key navigation.
 */
export function findNextOccupiedCellIndex(
  currentIndex: number,
  rows: number,
  cols: number,
  key: string,
  occupied: boolean[],
): number | null {
  const delta = ARROW_DELTAS[key];
  if (!delta) return null;
  const col = currentIndex % cols;
  const row = Math.floor(currentIndex / cols);
  let c = col + delta.dx;
  let r = row + delta.dy;
  while (c >= 0 && c < cols && r >= 0 && r < rows) {
    const index = r * cols + c;
    if (occupied[index]) return index;
    c += delta.dx;
    r += delta.dy;
  }
  return null;
}

export interface BoardGridDims {
  grid_rows?: number | null;
  grid_cols?: number | null;
}

/**
 * Index board symbols by cell, preserving the existing last-write-wins
 * behavior for malformed boards that contain duplicate placements.
 */
export function indexBoardSymbols(symbols: BoardSymbol[]): Map<string, BoardSymbol> {
  const symbolsByPosition = new Map<string, BoardSymbol>();
  for (const symbol of symbols) {
    symbolsByPosition.set(`${symbol.position_x}-${symbol.position_y}`, symbol);
  }
  return symbolsByPosition;
}

/** Return the defaulted grid capacity (rows x cols) of a board. */
export function getBoardCapacity(board: BoardGridDims): number {
  return (board.grid_rows ?? 4) * (board.grid_cols ?? 5);
}
