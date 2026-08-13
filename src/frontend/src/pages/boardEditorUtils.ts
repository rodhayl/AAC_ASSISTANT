import type { Board, BoardSymbol } from '../types';

export type BoardSymbolOverrides = Record<number, Partial<BoardSymbol>>;

export interface BoardPlayabilityStatus {
  playable: boolean;
  progress: number;
  needed: number;
  count: number;
  threshold: number;
}

export function mergeBoardSymbols(
  symbols: BoardSymbol[],
  overrides: BoardSymbolOverrides,
): BoardSymbol[] {
  return symbols.map((symbol) => ({
    ...symbol,
    ...overrides[symbol.id],
  }));
}

export function getBoardPlayabilityStatus(board: Board, symbols: BoardSymbol[]): BoardPlayabilityStatus {
  const capacity = (board.grid_rows ?? 4) * (board.grid_cols ?? 5);
  const threshold = Math.ceil(capacity * 0.5);
  const count = symbols.filter((symbol) =>
    symbol.is_visible && (symbol.custom_text || symbol.symbol?.label),
  ).length;
  const progress = threshold === 0 ? 0 : Math.round((count / threshold) * 100);

  return {
    playable: count >= threshold,
    progress,
    needed: Math.max(0, threshold - count),
    count,
    threshold,
  };
}
