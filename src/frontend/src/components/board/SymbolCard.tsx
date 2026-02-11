import { memo } from 'react';
import type { BoardSymbol } from '../../types';
import { Folder } from 'lucide-react';
import { SymbolImage } from '../common/SymbolImage';
import { useAccessibleInteraction } from '../../hooks/useAccessibleInteraction';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';

interface SymbolCardProps {
  boardSymbol: BoardSymbol;
  onClick: (boardSymbol: BoardSymbol) => void;
  disabled?: boolean;
}

export const SymbolCard = memo(function SymbolCard({ boardSymbol, onClick, disabled }: SymbolCardProps) {
  const label = boardSymbol.custom_text || boardSymbol.symbol.label;
  const categoryStyle = getCategoryStyle(boardSymbol.symbol?.category);

  const { onClick: handleClick, onMouseDown, onMouseUp, onMouseLeave, onTouchStart, onTouchEnd } = useAccessibleInteraction({
    onClick: () => !disabled && onClick(boardSymbol),
    disabled
  });

  return (
    <button
      type="button"
      onClick={handleClick}
      onMouseDown={onMouseDown}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseLeave}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      disabled={disabled}
      style={{ backgroundColor: boardSymbol.color }}
      className={`
        group relative flex flex-col items-center justify-center p-2 
        ${!boardSymbol.color ? 'glass-card' : ''}
        border-2 ${categoryStyle.border} rounded-xl 
        ${categoryStyle.hoverBorder}
        active:scale-95 transition-all duration-300 cursor-pointer w-full h-full
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
      aria-label={boardSymbol.linked_board_id ? `Open folder ${label}` : `Add ${label} to sentence`}
    >
      <div className={`absolute top-2 left-2 w-2.5 h-2.5 rounded-full ${categoryStyle.dot} opacity-80`} aria-hidden="true" />
      {boardSymbol.linked_board_id && (
        <div className="absolute top-2 right-2 z-10">
          <Folder className="w-6 h-6 text-indigo-500/80" />
        </div>
      )}

      {boardSymbol.symbol.image_path ? (
        <>
          <div className="w-full h-[65%] mb-1 bg-transparent rounded-lg flex items-center justify-center overflow-hidden p-1">
            <SymbolImage
              imagePath={boardSymbol.symbol.image_path}
              className="w-full h-full object-contain"
            />
          </div>
          <span className={`text-sm md:text-base font-bold text-center leading-tight break-words w-full line-clamp-2 px-1 h-[35%] flex items-center justify-center ${boardSymbol.color ? 'text-gray-900' : 'text-primary'}`}>
            {label}
          </span>
        </>
      ) : (
        <div className="w-full h-full flex flex-col items-center justify-center p-1 text-center overflow-hidden">
          <span className={`text-lg md:text-xl font-bold break-words w-full line-clamp-3 ${boardSymbol.color ? 'text-gray-900' : 'text-brand dark:text-indigo-300'}`}>
            {label}
          </span>
        </div>
      )}
    </button>
  );
});
