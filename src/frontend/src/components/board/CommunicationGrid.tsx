import { memo, useMemo, useRef } from 'react';
import type { BoardSymbol } from '../../types';
import { ARROW_DELTAS, findNextOccupiedCellIndex, indexBoardSymbols } from '../../lib/boardGrid';
import { SymbolCard } from './SymbolCard';

interface CommunicationGridProps {
  rows: number;
  cols: number;
  symbols: BoardSymbol[];
  onSymbolClick: (symbol: BoardSymbol) => void;
}

export const CommunicationGrid = memo(function CommunicationGrid({
  rows,
  cols,
  symbols,
  onSymbolClick,
}: CommunicationGridProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  const cells = useMemo(() => {
    const symbolsByPosition = indexBoardSymbols(symbols);
    return Array.from({ length: rows }).flatMap((_, row) =>
      Array.from({ length: cols }, (_, col) => {
        const key = `${col}-${row}`;
        return { key, symbol: symbolsByPosition.get(key) };
      }),
    );
  }, [cols, rows, symbols]);

  const occupied = useMemo(() => cells.map((cell) => cell.symbol != null), [cells]);

  // Arrow-key navigation between symbol cards: from the focused card's cell,
  // walk in the pressed direction to the next occupied cell and focus it.
  // Enter/Space activation needs no extra work — cards are native buttons.
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (!ARROW_DELTAS[event.key]) return;
    const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-cell-index]');
    if (!cell) return;
    const currentIndex = Number(cell.dataset.cellIndex);
    if (!Number.isFinite(currentIndex)) return;
    // Swallow the key even at the edge so the page does not scroll mid-scan.
    event.preventDefault();
    const next = findNextOccupiedCellIndex(currentIndex, rows, cols, event.key, occupied);
    if (next == null) return;
    gridRef.current
      ?.querySelector<HTMLElement>(`[data-cell-index="${next}"] button`)
      ?.focus();
  };

  return (
    <div
      ref={gridRef}
      onKeyDown={handleKeyDown}
      className="grid gap-2 mx-auto max-w-7xl pb-2"
      style={{
        gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
        minHeight: '100%',
      }}
    >
      {cells.map(({ key, symbol }, index) => (
        <div key={key} data-cell-index={index} className="w-full h-full min-h-[60px] sm:min-h-[70px] aspect-[1/0.8]">
          {symbol ? (
            <SymbolCard
              boardSymbol={symbol}
              onClick={onSymbolClick}
            />
          ) : (
            <div className="w-full h-full bg-muted/10 rounded-xl border border-dashed border-border/20" />
          )}
        </div>
      ))}
    </div>
  );
});
