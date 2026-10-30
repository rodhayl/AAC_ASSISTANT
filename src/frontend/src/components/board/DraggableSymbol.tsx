import { useDraggable } from '@dnd-kit/core';
import { memo } from 'react'
import { CSS } from '@dnd-kit/utilities';
import type { BoardSymbol } from '../../types';
import { GripVertical, Volume2, X, Pencil, Folder } from 'lucide-react';
import { tts } from '../../lib/tts';
import { SymbolImage } from '../common/SymbolImage';
import { useAuthStore } from '../../store/authStore';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';

interface DraggableSymbolProps {
  boardSymbol: BoardSymbol;
  isOverlay?: boolean;
  onRemove?: (id: number) => void;
  onEdit?: (symbol: BoardSymbol) => void;
}

function DraggableSymbolInner({ boardSymbol, isOverlay, onRemove, onEdit }: DraggableSymbolProps) {
  const { user } = useAuthStore();
  const categoryStyle = getCategoryStyle(boardSymbol.symbol?.category);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `symbol-${boardSymbol.id}`,
    data: boardSymbol
  });

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.5 : 1,
    cursor: isDragging ? 'grabbing' : 'grab',
    backgroundColor: boardSymbol.color || undefined,
  };

  const speak = async () => {
    if (user?.settings?.voice_mode_enabled === false) return;

    const text = boardSymbol.custom_text || boardSymbol.symbol.label;
    tts.enqueue(text, { key: boardSymbol.id });

    try {
      const api = (await import('../../lib/api')).default;
      await api.post('/analytics/log', {
        symbols: [{
          id: boardSymbol.symbol.id,
          label: boardSymbol.symbol.label,
          category: boardSymbol.symbol.category
        }]
      });
    } catch (e) {
      console.error('Failed to log symbol usage', e);
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className={`
        group relative flex flex-col items-center justify-center p-2 
        ${!boardSymbol.color ? 'bg-white dark:bg-gray-800' : ''} 
        border-2 ${categoryStyle.border} rounded-xl shadow-sm 
        ${categoryStyle.hoverBorder} hover:shadow-md transition-all
        ${isOverlay ? 'shadow-xl scale-105 z-50 cursor-grabbing' : ''}
        h-full w-full
      `}
    >
      <div className={`absolute top-2 left-2 w-2.5 h-2.5 rounded-full ${categoryStyle.dot} opacity-80`} aria-hidden="true" />
      {!isOverlay && (
        <div className="absolute top-1 right-1 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
          {onEdit && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onEdit(boardSymbol); }}
              className="p-1 rounded-md bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-800"
              aria-label="Edit symbol"
            >
              <Pencil className="w-4 h-4" />
            </button>
          )}
          {onRemove && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onRemove(boardSymbol.id); }}
              className="p-1 rounded-md bg-red-50 dark:bg-red-900/40 text-red-600 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-800"
              aria-label="Remove symbol"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <GripVertical className="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </div>
      )}

      {/* Linked Board Indicator */}
      {boardSymbol.linked_board_id && (
        <div className="absolute top-1 right-1 z-0">
          <Folder className="w-5 h-5 text-indigo-500/50" />
        </div>
      )}

      <button
        type="button"
        onClick={speak}
        className="absolute top-1 left-1 p-1 rounded-md bg-indigo-50 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-900"
        aria-label="Speak label"
      >
        <Volume2 className="w-4 h-4" />
      </button>

      <div className="w-16 h-16 mb-2 bg-transparent rounded-lg flex items-center justify-center overflow-hidden">
        <SymbolImage
          imagePath={boardSymbol.symbol.image_path}
          alt={boardSymbol.symbol.label}
          className="w-full h-full object-cover"
        />
      </div>

      <span className={`text-sm font-medium text-center leading-tight ${boardSymbol.color ? 'text-gray-900' : 'text-gray-900 dark:text-gray-100'
        }`}>
        {boardSymbol.custom_text || boardSymbol.symbol.label}
      </span>
    </div>
  );
}

export const DraggableSymbol = memo(DraggableSymbolInner)
