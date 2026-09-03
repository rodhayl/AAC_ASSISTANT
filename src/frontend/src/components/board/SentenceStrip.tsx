import { memo, useEffect, useRef, useState } from 'react';
import { Play, Delete, Trash2, X, Volume2, MessageSquare, ChevronLeft, ChevronRight } from 'lucide-react';
import { IconButton } from '../ui/icon-button';
import type { BoardSymbol } from '../../types';
import { useTranslation } from 'react-i18next';
import { SymbolImage } from '../common/SymbolImage';
import {
  DndContext,
  closestCenter,
  DragOverlay,
  useSensor,
  useSensors,
  PointerSensor,
  TouchSensor,
} from '@dnd-kit/core';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import { SortableContext, horizontalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
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
      data-testid="sentence-chip"
      className="flex-shrink-0 flex flex-col items-center bg-surface border border-border rounded-lg p-1.5 min-w-[4rem] relative group cursor-grab active:cursor-grabbing hover:border-brand transition-colors"
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
      <span className="text-xs font-medium text-foreground whitespace-nowrap max-w-[6rem] overflow-hidden text-ellipsis pointer-events-none">
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
  const sentenceScrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(String(event.active.id));
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

  useEffect(() => {
    const container = sentenceScrollRef.current;
    if (!container) return;

    const updateScrollControls = () => {
      const maxScrollLeft = container.scrollWidth - container.clientWidth;
      setCanScrollLeft(container.scrollLeft > 1);
      setCanScrollRight(maxScrollLeft - container.scrollLeft > 1);
    };

    updateScrollControls();
    container.addEventListener('scroll', updateScrollControls, { passive: true });
    window.addEventListener('resize', updateScrollControls);

    const resizeObserver = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(updateScrollControls)
      : null;
    resizeObserver?.observe(container);

    return () => {
      container.removeEventListener('scroll', updateScrollControls);
      window.removeEventListener('resize', updateScrollControls);
      resizeObserver?.disconnect();
    };
  }, [symbols]);

  const scrollSentence = (direction: 'left' | 'right') => {
    const container = sentenceScrollRef.current;
    if (!container) return;

    const distance = Math.max(container.clientWidth * 0.8, 160);
    container.scrollBy({
      left: direction === 'left' ? -distance : distance,
      behavior: 'smooth',
    });
  };

  return (
    <div data-testid="sentence-strip" className="glass-panel border-b border-border shadow-sm sticky top-0 z-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
        <div className="flex items-center gap-4">
          {/* Sentence Display Area */}
          <div className="flex min-w-0 flex-1 items-center gap-1">
            {(canScrollLeft || canScrollRight) && (
              <button
                type="button"
                onClick={() => scrollSentence('left')}
                disabled={!canScrollLeft}
                className="flex min-h-[2.75rem] min-w-[2.75rem] shrink-0 items-center justify-center rounded-full border border-brand/20 bg-surface text-brand transition-colors hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-30"
                aria-label={t('previousSentenceSymbols')}
                title={t('previousSentenceSymbols')}
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              </button>
            )}

            <div className="relative min-w-0 flex-1">
              {canScrollLeft && (
                <div
                  data-testid="sentence-left-overflow-indicator"
                  className="pointer-events-none absolute inset-y-0 left-0 z-10 w-8 bg-gradient-to-r from-brand/25 via-brand/10 to-transparent"
                  aria-hidden="true"
                />
              )}

              <div
                ref={sentenceScrollRef}
                data-testid="sentence-scroll-container"
                className="flex min-h-[5rem] min-w-0 items-center gap-2 overflow-x-auto rounded-xl border border-border bg-background p-2 hide-scrollbar touch-pan-x"
              >
            {symbols.length === 0 ? (
              <span data-testid="sentence-empty" className="text-muted-foreground px-2 italic select-none">
                {t('tapSymbolsToSpeak')}
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
                    <div className="flex-shrink-0 flex flex-col items-center bg-surface border-2 border-brand rounded-lg p-1.5 min-w-[4rem] shadow-xl opacity-90 scale-105">
                      {(() => {
                        const s = symbols.find((_, i) => `symbol-${_.id}-${i}` === activeId);
                        if (!s) return null;
                        return (
                          <>
                            <div className="w-8 h-8 mb-1">
                              <SymbolImage
                                imagePath={s.symbol.image_path}
                                className="w-full h-full object-contain"
                              />
                            </div>
                            <span className="text-xs font-medium text-foreground">
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

              {canScrollRight && (
                <div
                  data-testid="sentence-right-overflow-indicator"
                  className="pointer-events-none absolute inset-y-0 right-0 z-10 w-8 bg-gradient-to-l from-brand/25 via-brand/10 to-transparent"
                  aria-hidden="true"
                />
              )}
            </div>

            {(canScrollLeft || canScrollRight) && (
              <button
                type="button"
                onClick={() => scrollSentence('right')}
                disabled={!canScrollRight}
                className="flex min-h-[2.75rem] min-w-[2.75rem] shrink-0 items-center justify-center rounded-full border border-brand/20 bg-surface text-brand transition-colors hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-30"
                aria-label={t('nextSentenceSymbols')}
                title={t('nextSentenceSymbols')}
              >
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            {onBackspace && (
              <button
                onClick={onBackspace}
                disabled={symbols.length === 0}
                data-testid="sentence-backspace"
                className="p-3 rounded-xl bg-muted text-foreground hover:bg-surface-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                aria-label={t('backspace')}
              >
                <Delete className="w-6 h-6" />
              </button>
            )}

            <button
              onClick={onClear}
              disabled={symbols.length === 0}
              data-testid="sentence-clear"
              className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              aria-label={t('clearSentence')}
            >
              <Trash2 className="w-6 h-6" />
            </button>

            <button
              onClick={onSpeak}
              disabled={symbols.length === 0 || isSpeaking}
              data-testid="sentence-speak"
              className={`
                p-3 rounded-xl text-white shadow-sm transition-all transform active:scale-95
                ${isSpeaking
                  ? 'bg-brand/70 cursor-wait'
                  : 'bg-brand hover:bg-brand/80 hover:shadow-md'
                }
                ${symbols.length === 0 ? 'opacity-50 cursor-not-allowed bg-muted-foreground' : ''}
              `}
              aria-label={t('speakSentence')}
            >
              {isSpeaking ? (
                <Volume2 className="w-6 h-6 animate-pulse" />
              ) : (
                <Play className="w-6 h-6 fill-current" />
              )}
            </button>

            {onAskAI && (
              <IconButton
                label={t('askAI')}
                onClick={onAskAI}
                disabled={symbols.length === 0}
                data-testid="sentence-ask-ai"
                className="p-3 rounded-xl bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-900/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors size-11"
              >
                <MessageSquare className="w-6 h-6" />
              </IconButton>
            )}
          </div>
        </div>

        {/* Text Preview (for accessibility/clarity) */}
        {symbols.length > 0 && (
          <div data-testid="sentence-preview" className="mt-1 px-1 text-sm text-muted-foreground truncate">
            {sentenceText}
          </div>
        )}
      </div>
    </div>
  );
});
