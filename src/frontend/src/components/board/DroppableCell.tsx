import { useDroppable } from '@dnd-kit/core';
import { memo } from 'react'
import { Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface DroppableCellProps {
  x: number;
  y: number;
  children?: React.ReactNode;
  onAddClick?: () => void;
}

function DroppableCellInner({ x, y, children, onAddClick }: DroppableCellProps) {
  const { isOver, setNodeRef } = useDroppable({
    id: `cell-${x}-${y}`,
    data: { x, y }
  });
  const { t } = useTranslation('boards');

  return (
    <div
      ref={setNodeRef}
      role="gridcell"
      tabIndex={0}
      aria-label={t('cellPosition', { x, y })}
      className={`
        aspect-square rounded-xl border-2 border-dashed transition-all
        flex items-center justify-center p-2
        ${isOver 
          ? 'border-brand bg-brand/10'
          : children 
            ? 'border-transparent bg-transparent' 
            : 'border-border hover:border-brand hover:bg-surface-hover'
        }
      `}
    >
      {children ? (
        children
      ) : (
        <button
          onClick={onAddClick}
          className="w-full h-full flex items-center justify-center text-muted-foreground hover:text-brand transition-colors"
          aria-label={t('addSymbol')}
        >
          <Plus className="w-8 h-8" />
        </button>
      )}
    </div>
  );
}

export const DroppableCell = memo(DroppableCellInner)
