import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, Brain, Type, User, Play, FileText, Plus, MapPin, ChevronLeft, ChevronRight } from 'lucide-react';
import api from '../../lib/api';
import { SymbolImage } from '../common/SymbolImage';
import { useHoverSpeak } from '../../hooks/useHoverSpeak';
import { useLearningStore } from '../../store/learningStore';
import type { BoardSymbol } from '../../types';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';

interface SmartbarProps {
  currentSentence: BoardSymbol[];
  onSelectSymbol: (symbol: BoardSymbol) => void;
  boardId?: number | null;
  /** Session/topic context so predictions match the subject under study. */
  topic?: string | null;
}

interface Suggestion {
  symbol_id: number;
  label: string;
  category: string;
  image_path?: string;
  color?: string;
  confidence: number;
  source?: 'ai' | 'stats' | 'category' | 'punctuation';
}

type IntentType = 'general' | 'pronouns' | 'verbs' | 'articles' | 'nouns' | 'places';

// Delay before fetching predictions after the sentence changes. Typing a word
// fires many rapid `currentSentence` updates; debouncing collapses them into a
// single request without delaying explicit intent/pagination changes.
const SMARTBAR_DEBOUNCE_MS = 300;

export function Smartbar({ currentSentence, onSelectSymbol, boardId, topic }: SmartbarProps) {
  const { t, i18n } = useTranslation('boards');
  const currentLanguage = i18n?.language?.split('-')[0] || 'en';
  const messages = useLearningStore((state) => state.messages);
  const { getHoverSpeakProps } = useHoverSpeak();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [activeIntent, setActiveIntent] = useState<IntentType>('general');
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [debouncedSentence, setDebouncedSentence] = useState(currentSentence);
  const suggestionsContainerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const SUGGESTIONS_PAGE_SIZE = 20;

  // Collapse rapid sentence updates into one prediction fetch.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSentence(currentSentence), SMARTBAR_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [currentSentence]);

  // Helper to switch intent cleanly
  const handleIntentChange = (intent: IntentType) => {
    if (intent === activeIntent) return;
    setSuggestions([]); // Clear immediately
    setOffset(0);       // Reset offset
    setActiveIntent(intent);
  };

  // Reset pagination when context changes
  useEffect(() => {
    setOffset(0);
  }, [currentSentence]);

  useEffect(() => {
    let active = true; // Flag to prevent stale updates
    const controller = new AbortController();

    const mergeSuggestions = (prev: Suggestion[], incoming: Suggestion[]) => {
      const merged: Suggestion[] = [...prev];
      const labelIndex = new Map<string, number>();
      const norm = (s: Suggestion) => (s.label || '').trim().toLowerCase();

      for (let i = 0; i < merged.length; i++) {
        const key = norm(merged[i]);
        if (key) labelIndex.set(key, i);
      }

      for (const next of incoming) {
        const key = norm(next);
        if (!key) continue;

        const existingIdx = labelIndex.get(key);
        if (existingIdx === undefined) {
          labelIndex.set(key, merged.length);
          merged.push(next);
          continue;
        }

        // Prefer the version that has an image (better UX consistency).
        const existing = merged[existingIdx];
        if (!existing.image_path && next.image_path) {
          merged[existingIdx] = next;
        }
      }

      return merged;
    };

    const fetchSuggestions = async () => {
      setIsLoading(true);
      try {
        const labels = debouncedSentence
          .map(s => s.custom_text || s.symbol.label)
          .join(',');

        // Use last 5 messages for context
        const chatHistory = messages.slice(-5).map(m => ({
          role: m.role,
          content: m.content
        }));

        // Use POST for AI-enhanced prediction
        const response = await api.post('/analytics/next-symbol', {
          current_symbols: labels,
          chat_history: chatHistory,
          limit: SUGGESTIONS_PAGE_SIZE,
          intent: activeIntent,
          offset: offset,
          board_id: boardId ?? undefined,
          topic: topic ?? undefined,
        }, { signal: controller.signal });

        if (active) {
          // If offset > 0, append; otherwise replace
          if (offset > 0) {
            setSuggestions(prev => mergeSuggestions(prev, response.data));
          } else {
            setSuggestions(mergeSuggestions([], response.data));
          }
          // A short page means the backend has nothing left to offer, so the
          // "More" button must not keep re-fetching the same items.
          setHasMore(Array.isArray(response.data) && response.data.length >= SUGGESTIONS_PAGE_SIZE);
        }
      } catch (error) {
        if (active && (error as { code?: string })?.code !== 'ERR_CANCELED') {
          console.error('Failed to fetch suggestions:', error);
          if (offset === 0) setSuggestions([]);
        }
      } finally {
        if (active) setIsLoading(false);
      }
    };

    fetchSuggestions();

    return () => {
      active = false;
      controller.abort();
    };
  }, [debouncedSentence, messages, activeIntent, offset, boardId, topic]); // Re-fetch when sentence OR chat updates

  useEffect(() => {
    const container = suggestionsContainerRef.current;
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
  }, [suggestions]);

  const scrollSuggestions = (direction: 'left' | 'right') => {
    const container = suggestionsContainerRef.current;
    if (!container) return;

    const distance = Math.max(container.clientWidth * 0.8, 160);
    container.scrollBy({
      left: direction === 'left' ? -distance : distance,
      behavior: 'smooth',
    });
  };

  const handleMore = () => {
    setOffset(prev => prev + SUGGESTIONS_PAGE_SIZE);
  };

  // Always render to allow access to categories

  return (
    <div className="w-full min-w-0 bg-brand/10 border-b border-brand/20 p-1.5 transition-all">
      <div className="flex items-center justify-between gap-2 mb-1.5 px-1 overflow-x-auto">
        <div className="flex items-center gap-1.5 shrink-0">
          <Sparkles className="w-3.5 h-3.5 text-brand animate-pulse" />
          <span className="text-[10px] font-medium text-brand uppercase tracking-wider hidden sm:inline">
            {t('suggestions')}
          </span>
        </div>

        <div className="flex gap-1">
          <button
            onClick={() => handleIntentChange('general')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'general'
              ? 'bg-brand text-white shadow-sm'
              : 'glass-card text-muted-foreground hover:bg-brand/10'
              }`}
          >
            <Brain className="w-3 h-3" />
            <span className="hidden sm:inline">{t('ai')}</span>
          </button>
          <button
            onClick={() => handleIntentChange('pronouns')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'pronouns'
              ? 'bg-brand text-white shadow-sm'
              : 'glass-card text-muted-foreground hover:bg-brand/10'
              }`}
          >
            <User className="w-3 h-3" />
            <span className="hidden sm:inline">{t('pronouns')}</span>
          </button>
          <button
            onClick={() => handleIntentChange('verbs')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'verbs'
              ? 'bg-brand text-white shadow-sm'
              : 'glass-card text-muted-foreground hover:bg-brand/10'
              }`}
          >
            <Play className="w-3 h-3" />
            <span className="hidden sm:inline">{t('verbs')}</span>
          </button>
          <button
            onClick={() => handleIntentChange('nouns')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'nouns'
              ? 'bg-brand text-white shadow-sm'
              : 'glass-card text-muted-foreground hover:bg-brand/10'
              }`}
          >
            <Type className="w-3 h-3" />
            <span className="hidden sm:inline">{t('nouns')}</span>
          </button>
          <button
            onClick={() => handleIntentChange('articles')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'articles'
              ? 'bg-brand text-white shadow-sm'
              : 'glass-card text-muted-foreground hover:bg-brand/10'
              }`}
          >
            <FileText className="w-3 h-3" />
            <span className="hidden sm:inline">{t('articles')}</span>
          </button>

          <button
            onClick={() => handleIntentChange('places')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'places'
              ? 'bg-brand text-white shadow-sm'
              : 'glass-card text-muted-foreground hover:bg-brand/10'
              }`}
          >
            <MapPin className="w-3 h-3" />
            <span className="hidden sm:inline">{t('places')}</span>
          </button>

          {/* More Button */}
          <button
            onClick={handleMore}
            disabled={isLoading || !hasMore}
            className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-surface text-brand hover:bg-brand/10 transition-colors flex items-center gap-1 border border-brand/20 disabled:opacity-50"
            title={t('moreSuggestions')}
          >
            <Plus className="w-3 h-3" />
            <span className="hidden sm:inline">{t('more')}</span>
          </button>
        </div>
      </div>

      {isLoading && offset === 0 ? (
        <div className="flex justify-center items-center h-16 text-brand">
          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-brand" />
        </div>
      ) : suggestions.length > 0 ? (
        <div className="flex w-full max-w-full min-w-0 items-center gap-1 overflow-hidden px-1">
          {(canScrollLeft || canScrollRight) && (
            <button
              type="button"
              onClick={() => scrollSuggestions('left')}
              disabled={!canScrollLeft}
              className="flex min-h-[2.75rem] min-w-[2.75rem] shrink-0 items-center justify-center rounded-full border border-brand/20 bg-surface text-brand transition-colors hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-30"
              aria-label={t('previousSuggestions')}
              title={t('previousSuggestions')}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </button>
          )}

          <div className="relative min-w-0 flex-1">
            {canScrollLeft && (
              <div
                data-testid="smartbar-left-overflow-indicator"
                className="pointer-events-none absolute inset-y-0 left-0 z-10 w-8 bg-gradient-to-r from-brand/25 via-brand/10 to-transparent"
                aria-hidden="true"
              />
            )}

            <div
              ref={suggestionsContainerRef}
              data-testid="smartbar-suggestions"
              className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-2 scrollbar-hide touch-pan-x"
            >
            {suggestions.map((suggestion, suggestionIndex) => {
            const isAI = suggestion.source === 'ai';
            const isPunctuation = suggestion.category === 'punctuation';
            const categoryStyle = getCategoryStyle(suggestion.category);

            return (
              <div
                key={`${suggestion.symbol_id}-${suggestionIndex}`}
                className="relative shrink-0"
              >
                <button
                  // Punctuation tiles hide their label visually; hovering
                  // them has no word worth speaking.
                  {...getHoverSpeakProps(isPunctuation ? '' : suggestion.label)}
                  onClick={() => {
                    const tempSymbol: BoardSymbol = {
                      id: -suggestion.symbol_id,
                      symbol_id: suggestion.symbol_id,
                      position_x: 0,
                      position_y: 0,
                      size: 1,
                      is_visible: true,
                      custom_text: suggestion.label,
                      symbol: {
                        id: suggestion.symbol_id,
                        label: suggestion.label,
                        image_path: suggestion.image_path,
                        category: suggestion.category,
                        description: '',
                        keywords: '',
                        audio_path: '',
                        language: currentLanguage,
                        is_builtin: false,
                        is_in_use: true,
                        created_at: new Date().toISOString()
                      }
                    };
                    onSelectSymbol(tempSymbol);
                  }}
                  style={{ backgroundColor: suggestion.color }}
                  className={`
                    h-14 sm:h-[4.5rem] min-w-[4rem] px-3
                    flex flex-col items-center justify-center relative overflow-hidden
                    ${!suggestion.color ? 'bg-surface' : ''}
                    border-2 ${categoryStyle.border}
                    rounded-xl shadow-sm 
                    ${categoryStyle.hoverBorder} hover:shadow-md 
                    active:scale-95 transition-all
                  `}
                >
                  <div className={`absolute top-1.5 left-1.5 w-2 h-2 rounded-full ${categoryStyle.dot} opacity-80`} aria-hidden="true" />
                  <div className="h-[60%] w-full flex items-center justify-center mb-1">
                    <SymbolImage
                      imagePath={suggestion.image_path}
                      alt={suggestion.label}
                      className="h-full w-auto object-contain"
                      missingImageLabel={t('imageUnavailable')}
                    />
                  </div>
                  <span className={`text-xs font-bold leading-tight text-center w-full px-1 ${isPunctuation ? 'sr-only' : ''} text-foreground line-clamp-2`}>
                    {suggestion.label}
                  </span>
                </button>

                {isAI && (
                  <div className="absolute -top-1 -right-1 bg-purple-500 text-white rounded-full p-0.5 shadow-sm z-10 pointer-events-none" title={t('aiSuggestionTitle')}>
                    <Brain className="w-2.5 h-2.5" />
                  </div>
                )}
              </div>
            );
            })}
            </div>

            {canScrollRight && (
              <div
                data-testid="smartbar-right-overflow-indicator"
                className="pointer-events-none absolute inset-y-0 right-0 z-10 w-8 bg-gradient-to-l from-brand/25 via-brand/10 to-transparent"
                aria-hidden="true"
              />
            )}
          </div>

          {(canScrollLeft || canScrollRight) && (
            <button
              type="button"
              onClick={() => scrollSuggestions('right')}
              disabled={!canScrollRight}
              className="flex min-h-[2.75rem] min-w-[2.75rem] shrink-0 items-center justify-center rounded-full border border-brand/20 bg-surface text-brand transition-colors hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-30"
              aria-label={t('nextSuggestions')}
              title={t('nextSuggestions')}
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      ) : (
        <div className="text-center py-2 text-muted-foreground text-xs">
          {t('noSuggestions')}
        </div>
      )}
    </div>
  );
}
