import { memo, useMemo } from 'react';
import type { BoardSymbol } from '../../types';
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
  const cells = useMemo(() => {
    return Array.from({ length: rows }).flatMap((_, row) =>
      Array.from({ length: cols }, (_, col) => ({
        key: `${col}-${row}`,
        symbol: symbols.find((candidate) =>
          candidate.position_x === col && candidate.position_y === row
        ),
      }))
    );
  }, [cols, rows, symbols]);

  return (
    <div
      className="grid gap-2 mx-auto max-w-7xl pb-2"
      style={{
        gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
        minHeight: '100%',
      }}
    >
      {cells.map(({ key, symbol }) => (
        <div key={key} className="w-full h-full min-h-[60px] sm:min-h-[70px] aspect-[1/0.8]">
          {symbol ? (
            <SymbolCard
              boardSymbol={symbol}
              onClick={onSymbolClick}
            />
          ) : (
            <div className="w-full h-full bg-gray-200/10 dark:bg-gray-800/10 rounded-xl border border-dashed border-gray-300/20 dark:border-gray-700/20" />
          )}
        </div>
      ))}
    </div>
  );
});
