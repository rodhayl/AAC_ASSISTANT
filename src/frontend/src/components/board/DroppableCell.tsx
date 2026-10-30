import { useDroppable } from '@dnd-kit/core';
import { memo } from 'react'
import { Plus } from 'lucide-react';

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

  return (
    <div
      ref={setNodeRef}
      role="gridcell"
      tabIndex={0}
      aria-label={`Cell ${x}, ${y}`}
      className={`
        aspect-square rounded-xl border-2 border-dashed transition-all
        flex items-center justify-center p-2
        ${isOver 
          ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30' 
          : children 
            ? 'border-transparent bg-transparent' 
            : 'border-gray-200 dark:border-gray-600 hover:border-indigo-300 dark:hover:border-indigo-500 hover:bg-gray-50 dark:hover:bg-gray-700'
        }
      `}
    >
      {children ? (
        children
      ) : (
        <button
          onClick={onAddClick}
          className="w-full h-full flex items-center justify-center text-gray-300 dark:text-gray-500 hover:text-indigo-500 dark:hover:text-indigo-400 transition-colors"
          aria-label="Add symbol"
        >
          <Plus className="w-8 h-8" />
        </button>
      )}
    </div>
  );
}

export const DroppableCell = memo(DroppableCellInner)
