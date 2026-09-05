import { useDraggable } from '@dnd-kit/core';
import { memo } from 'react'
import { CSS } from '@dnd-kit/utilities';
import type { BoardSymbol } from '../../types';
import { GripVertical, Volume2, X, Pencil, Folder } from 'lucide-react';
import { tts } from '../../lib/tts';
import { SymbolImage } from '../common/SymbolImage';
import { useAuthStore } from '../../store/authStore';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';
import { useTranslation } from 'react-i18next';
import { cn } from '../../lib/utils';

interface DraggableSymbolProps {
  boardSymbol: BoardSymbol;
  isOverlay?: boolean;
  onRemove?: (id: number) => void;
  onEdit?: (symbol: BoardSymbol) => void;
}

function DraggableSymbolInner({ boardSymbol, isOverlay, onRemove, onEdit }: DraggableSymbolProps) {
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('boards');
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
      await api.post('/analytics/usage', {
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
      className={cn(
        'group relative flex h-full w-full flex-col items-center justify-center rounded-xl border-2 p-2 shadow-sm transition-all',
        !boardSymbol.color && 'bg-surface',
        categoryStyle.border,
        categoryStyle.hoverBorder,
        'hover:shadow-md',
        isOverlay && 'z-50 scale-105 cursor-grabbing shadow-xl',
      )}
    >
      <div className={cn('absolute top-2 left-2 h-2.5 w-2.5 rounded-full opacity-80', categoryStyle.dot)} aria-hidden="true" />
      {!isOverlay && (
        <div className="absolute top-1 right-1 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
          {onEdit && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onEdit(boardSymbol); }}
              className="p-1 rounded-md bg-brand/10 text-brand hover:bg-brand/20"
              aria-label={t('editSymbol')}
            >
              <Pencil className="w-4 h-4" />
            </button>
          )}
          {onRemove && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onRemove(boardSymbol.id); }}
              className="p-1 rounded-md bg-destructive/10 text-destructive hover:bg-destructive/20"
              aria-label={t('removeSymbol')}
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <GripVertical className="w-4 h-4 text-muted-foreground" />
        </div>
      )}

      {/* Linked Board Indicator */}
      {boardSymbol.linked_board_id && (
        <div className="absolute top-1 right-1 z-0">
          <Folder className="w-5 h-5 text-brand/50" />
        </div>
      )}

      <button
        type="button"
        onClick={speak}
        className="absolute top-1 left-1 p-1 rounded-md bg-brand/10 text-brand hover:bg-brand/20"
        aria-label={t('speakLabel')}
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

      <span className="text-center text-sm font-medium leading-tight text-foreground">
        {boardSymbol.custom_text || boardSymbol.symbol.label}
      </span>
    </div>
  );
}

export const DraggableSymbol = memo(DraggableSymbolInner)
