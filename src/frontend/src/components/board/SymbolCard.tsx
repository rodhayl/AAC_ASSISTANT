import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import type { BoardSymbol } from '../../types';
import { Folder } from 'lucide-react';
import { SymbolImage } from '../common/SymbolImage';
import { useAccessibleInteraction } from '../../hooks/useAccessibleInteraction';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';
import { cn } from '@/lib/utils';

interface SymbolCardProps {
  boardSymbol: BoardSymbol;
  onClick: (boardSymbol: BoardSymbol) => void;
  disabled?: boolean;
  ariaLabel?: string;
}

export const SymbolCard = memo(function SymbolCard({ boardSymbol, onClick, disabled, ariaLabel }: SymbolCardProps) {
  const { t } = useTranslation('boards');
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
      className={cn(
        'group relative flex h-full w-full cursor-pointer flex-col items-center justify-center rounded-xl border-2 p-2 transition-all duration-300 active:scale-95',
        !boardSymbol.color && 'glass-card',
        categoryStyle.border,
        categoryStyle.hoverBorder,
        disabled && 'cursor-not-allowed opacity-50',
      )}
      aria-label={ariaLabel ?? (boardSymbol.linked_board_id
        ? t('openFolder', { label })
        : t('addToSentence', { label }))}
    >
      <div className={cn('absolute left-2 top-2 h-2.5 w-2.5 rounded-full opacity-80', categoryStyle.dot)} aria-hidden="true" />
      {boardSymbol.linked_board_id && (
        <div className="absolute top-2 right-2 z-10">
          <Folder className="w-6 h-6 text-brand/80" />
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
          <span className="text-sm md:text-base font-bold text-center leading-tight break-words w-full line-clamp-2 px-1 h-[35%] flex items-center justify-center text-foreground">
            {label}
          </span>
        </>
      ) : (
        <div className="w-full h-full flex flex-col items-center justify-center p-1 text-center overflow-hidden">
          <span className={cn('text-lg md:text-xl font-bold break-words w-full line-clamp-3', boardSymbol.color ? 'text-foreground' : 'text-brand')}>
            {label}
          </span>
        </div>
      )}
    </button>
  );
});
