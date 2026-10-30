import { memo } from 'react';
import { Play, Delete, Trash2, X, Volume2, MessageSquare } from 'lucide-react';
import type { BoardSymbol } from '../../types';
import { useTranslation } from 'react-i18next';
import { SymbolImage } from '../common/SymbolImage';
import { DndContext, closestCenter, DragOverlay, useSensor, useSensors, MouseSensor, TouchSensor } from '@dnd-kit/core';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import { SortableContext, horizontalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useState } from 'react';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';

interface SentenceStripProps {
  symbols: BoardSymbol[];
  onRemove: (index: number) => void;
  onClear: () => void;
  onBackspace?: () => void;
  onSpeak: () => void;
  onSpeakItem?: (text: string) => void;
  onReorder?: (fromIndex: number, toIndex: number) => void;
  onAskAI?: () => void;
  isSpeaking: boolean;
}

function SortableSymbol({ symbol, index, onRemove, onSpeakItem }: {
  symbol: BoardSymbol,
  index: number,
  onRemove: (idx: number) => void,
  onSpeakItem?: (text: string) => void
}) {
  const categoryStyle = getCategoryStyle(symbol.symbol?.category);
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({ id: `symbol-${symbol.id}-${index}` });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className="flex-shrink-0 flex flex-col items-center bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-1.5 min-w-[4rem] relative group cursor-grab active:cursor-grabbing hover:border-indigo-500 transition-colors"
      onClick={() => {
        // If we are dragging, don't trigger speak
        if (!isDragging) onSpeakItem?.(symbol.custom_text || symbol.symbol.label);
      }}
    >
      <div className={`absolute top-1 left-1 w-2 h-2 rounded-full ${categoryStyle.dot} opacity-80`} aria-hidden="true" />
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRemove(index);
        }}
        // Use pointer-events-auto to ensure click is captured even with dnd listeners
        className="absolute -top-2 -right-2 bg-red-100 dark:bg-red-900 text-red-600 dark:text-red-300 rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity shadow-sm z-10 cursor-pointer"
        onPointerDown={(e) => e.stopPropagation()} // Prevent drag start on close button
      >
        <X className="w-3 h-3" />
      </button>
      <div className="w-8 h-8 mb-1 pointer-events-none">
        <SymbolImage
          imagePath={symbol.symbol.image_path}
          className="w-full h-full object-contain"
        />
      </div>
      <span className="text-xs font-medium text-gray-900 dark:text-gray-100 whitespace-nowrap max-w-[6rem] overflow-hidden text-ellipsis pointer-events-none">
        {symbol.custom_text || symbol.symbol.label}
      </span>
    </div>
  );
}

export const SentenceStrip = memo(function SentenceStrip({
  symbols,
  onRemove,
  onClear,
  onBackspace,
  onSpeak,
  onSpeakItem,
  onReorder,
  onAskAI,
  isSpeaking
}: SentenceStripProps) {
  const { t } = useTranslation('boards');
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);

    if (over && active.id !== over.id && onReorder) {
      // Fix: match the ID format used in SortableContext
      const oldIndex = symbols.findIndex((_, i) => `symbol-${_.id}-${i}` === active.id);
      const newIndex = symbols.findIndex((_, i) => `symbol-${_.id}-${i}` === over.id);

      // Add additional safety check
      if (oldIndex !== -1 && newIndex !== -1 && oldIndex !== newIndex) {
        onReorder(oldIndex, newIndex);
      }
    }
  };

  const sentenceText = symbols.map(s => s.custom_text || s.symbol.label).join(' ');

  return (
    <div className="glass-panel border-b border-border dark:border-white/5 shadow-sm sticky top-0 z-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
        <div className="flex items-center gap-4">
          {/* Sentence Display Area */}
          <div className="flex-1 min-h-[5rem] bg-gray-50 dark:bg-white/5 rounded-xl border border-border dark:border-white/5 p-2 flex items-center gap-2 overflow-x-auto hide-scrollbar touch-pan-x">
            {symbols.length === 0 ? (
              <span className="text-gray-400 dark:text-gray-500 px-2 italic select-none">
                {t('tapSymbolsToSpeak', 'Tap symbols to create a sentence...')}
              </span>
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={symbols.map((s, i) => `symbol-${s.id}-${i}`)}
                  strategy={horizontalListSortingStrategy}
                >
                  {symbols.map((s, idx) => (
                    <SortableSymbol
                      key={`symbol-${s.id}-${idx}`}
                      symbol={s}
                      index={idx}
                      onRemove={onRemove}
                      onSpeakItem={onSpeakItem}
                    />
                  ))}
                </SortableContext>

                {/* Drag Overlay for visual feedback */}
                <DragOverlay>
                  {activeId ? (
                    <div className="flex-shrink-0 flex flex-col items-center bg-white dark:bg-gray-800 border-2 border-indigo-500 rounded-lg p-1.5 min-w-[4rem] shadow-xl opacity-90 scale-105">
                      {(() => {
                        const s = symbols.find((_, i) => `${_.id}-${i}` === activeId);
                        if (!s) return null;
                        return (
                          <>
                            <div className="w-8 h-8 mb-1">
                              <SymbolImage
                                imagePath={s.symbol.image_path}
                                className="w-full h-full object-contain"
                              />
                            </div>
                            <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                              {s.custom_text || s.symbol.label}
                            </span>
                          </>
                        );
                      })()}
                    </div>
                  ) : null}
                </DragOverlay>
              </DndContext>
            )}
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            {onBackspace && (
              <button
                onClick={onBackspace}
                disabled={symbols.length === 0}
                className="p-3 rounded-xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                aria-label={t('backspace', 'Backspace')}
              >
                <Delete className="w-6 h-6" />
              </button>
            )}

            <button
              onClick={onClear}
              disabled={symbols.length === 0}
              className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              aria-label={t('clearSentence', 'Clear sentence')}
            >
              <Trash2 className="w-6 h-6" />
            </button>

            <button
              onClick={onSpeak}
              disabled={symbols.length === 0 || isSpeaking}
              className={`
                p-3 rounded-xl text-white shadow-sm transition-all transform active:scale-95
                ${isSpeaking
                  ? 'bg-indigo-400 cursor-wait'
                  : 'bg-indigo-600 hover:bg-indigo-700 hover:shadow-md'
                }
                ${symbols.length === 0 ? 'opacity-50 cursor-not-allowed bg-gray-400 dark:bg-gray-600' : ''}
              `}
              aria-label={t('speakSentence', 'Speak sentence')}
            >
              {isSpeaking ? (
                <Volume2 className="w-6 h-6 animate-pulse" />
              ) : (
                <Play className="w-6 h-6 fill-current" />
              )}
            </button>

            {onAskAI && (
              <button
                onClick={onAskAI}
                disabled={symbols.length === 0}
                className="p-3 rounded-xl bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-900/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={t('askAI', 'Ask AI')}
              >
                <MessageSquare className="w-6 h-6" />
              </button>
            )}
          </div>
        </div>

        {/* Text Preview (for accessibility/clarity) */}
        {symbols.length > 0 && (
          <div className="mt-1 px-1 text-sm text-gray-500 dark:text-gray-400 truncate">
            {sentenceText}
          </div>
        )}
      </div>
    </div>
  );
});
