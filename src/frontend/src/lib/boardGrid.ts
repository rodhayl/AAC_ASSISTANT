import type { BoardSymbol } from '../types';

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
