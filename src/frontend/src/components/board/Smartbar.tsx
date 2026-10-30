import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, Brain, Type, User, Play, FileText, Plus, MapPin, Image as ImageIcon } from 'lucide-react';
import api from '../../lib/api';
import { SymbolImage } from '../common/SymbolImage';
import { useLearningStore } from '../../store/learningStore';
import type { BoardSymbol } from '../../types';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';

interface SmartbarProps {
  currentSentence: BoardSymbol[];
  onSelectSymbol: (symbol: BoardSymbol) => void;
  boardId?: number | null;
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

export function Smartbar({ currentSentence, onSelectSymbol, boardId }: SmartbarProps) {
  const { t } = useTranslation('boards');
  const { messages } = useLearningStore();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [activeIntent, setActiveIntent] = useState<IntentType>('general');
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

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
        const labels = currentSentence
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
          limit: 20,
          intent: activeIntent,
          offset: offset,
          board_id: boardId ?? undefined,
        });

        if (active) {
          // If offset > 0, append; otherwise replace
          if (offset > 0) {
            setSuggestions(prev => mergeSuggestions(prev, response.data));
          } else {
            setSuggestions(mergeSuggestions([], response.data));
          }
        }
      } catch (error) {
        if (active) {
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
    };
  }, [currentSentence, messages, activeIntent, offset, boardId]); // Re-fetch when sentence OR chat updates

  const handleMore = () => {
    setOffset(prev => prev + 20);
  };

  // Always render to allow access to categories
  // if (suggestions.length === 0 && activeIntent === 'general') return null;

  return (
    <div className="w-full bg-indigo-50 dark:bg-indigo-900/20 border-b border-indigo-100 dark:border-indigo-800/50 p-1.5 transition-all">
      <div className="flex items-center justify-between gap-2 mb-1.5 px-1 overflow-x-auto">
        <div className="flex items-center gap-1.5 shrink-0">
          <Sparkles className="w-3.5 h-3.5 text-indigo-500 animate-pulse" />
          <span className="text-[10px] font-medium text-indigo-600 dark:text-indigo-300 uppercase tracking-wider hidden sm:inline">
            {t('suggestions', 'Suggestions')}
          </span>
        </div>

        <div className="flex gap-1">
          <button
            onClick={() => handleIntentChange('general')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'general'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'glass-card text-gray-600 dark:text-gray-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50'
              }`}
          >
            <Brain className="w-3 h-3" />
            <span className="hidden sm:inline">AI</span>
          </button>
          <button
            onClick={() => handleIntentChange('pronouns')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'pronouns'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'glass-card text-gray-600 dark:text-gray-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50'
              }`}
          >
            <User className="w-3 h-3" />
            <span className="hidden sm:inline">{t('pronouns', 'Pronouns')}</span>
          </button>
          <button
            onClick={() => handleIntentChange('verbs')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'verbs'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'glass-card text-gray-600 dark:text-gray-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50'
              }`}
          >
            <Play className="w-3 h-3" />
            <span className="hidden sm:inline">{t('verbs', 'Verbs')}</span>
          </button>
          <button
            onClick={() => handleIntentChange('nouns')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'nouns'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'glass-card text-gray-600 dark:text-gray-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50'
              }`}
          >
            <Type className="w-3 h-3" />
            <span className="hidden sm:inline">{t('nouns', 'Nouns')}</span>
          </button>
          <button
            onClick={() => handleIntentChange('articles')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'articles'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'glass-card text-gray-600 dark:text-gray-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50'
              }`}
          >
            <FileText className="w-3 h-3" />
            <span className="hidden sm:inline">{t('articles', 'Articles')}</span>
          </button>

          <button
            onClick={() => handleIntentChange('places')}
            className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1 ${activeIntent === 'places'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'glass-card text-gray-600 dark:text-gray-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50'
              }`}
          >
            <MapPin className="w-3 h-3" />
            <span className="hidden sm:inline">{t('places', 'Places')}</span>
          </button>

          {/* More Button */}
          <button
            onClick={handleMore}
            disabled={isLoading}
            className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/50 transition-colors flex items-center gap-1 border border-indigo-100 dark:border-indigo-800 disabled:opacity-50"
            title={t('moreSuggestions', 'More suggestions')}
          >
            <Plus className="w-3 h-3" />
            <span className="hidden sm:inline">{t('more', 'More')}</span>
          </button>
        </div>
      </div>

      {isLoading && offset === 0 ? (
        <div className="flex justify-center items-center h-16 text-indigo-500">
          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-600" />
        </div>
      ) : suggestions.length > 0 ? (
        <div className="flex gap-2 overflow-x-auto pb-2 px-1 scrollbar-hide">
          {suggestions.map((suggestion) => {
            const isAI = suggestion.source === 'ai';
            const isPunctuation = suggestion.category === 'punctuation';
            const categoryStyle = getCategoryStyle(suggestion.category);

            return (
              <div
                key={suggestion.symbol_id}
                className="relative shrink-0"
              >
                <button
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
                        language: 'en',
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
                    ${!suggestion.color ? 'bg-white dark:bg-gray-800' : ''}
                    border-2 ${categoryStyle.border}
                    rounded-xl shadow-sm 
                    ${categoryStyle.hoverBorder} hover:shadow-md 
                    active:scale-95 transition-all
                  `}
                >
                  <div className={`absolute top-1.5 left-1.5 w-2 h-2 rounded-full ${categoryStyle.dot} opacity-80`} aria-hidden="true" />
                  <div className="h-[60%] w-full flex items-center justify-center mb-1">
                    {suggestion.image_path ? (
                      <SymbolImage
                        imagePath={suggestion.image_path}
                        alt={suggestion.label}
                        className="h-full w-auto object-contain"
                      />
                    ) : (
                      <div className={`flex items-center justify-center ${isPunctuation ? 'text-2xl' : 'text-base'} font-bold ${suggestion.color ? 'text-gray-900' : 'text-gray-900 dark:text-gray-100'}`}>
                        {isPunctuation ? suggestion.label : <ImageIcon className="w-4 h-4 opacity-60" />}
                      </div>
                    )}
                  </div>
                  <span className={`text-xs font-bold leading-tight text-center w-full px-1 ${isPunctuation ? 'sr-only' : ''} ${suggestion.color ? 'text-gray-900' : 'text-gray-900 dark:text-gray-100'} line-clamp-2`}>
                    {suggestion.label}
                  </span>
                </button>

                {isAI && (
                  <div className="absolute -top-1 -right-1 bg-purple-500 text-white rounded-full p-0.5 shadow-sm z-10 pointer-events-none" title="AI Suggestion">
                    <Brain className="w-2.5 h-2.5" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-2 text-gray-400 text-xs">
          {t('noSuggestions', 'No suggestions found')}
        </div>
      )}
    </div>
  );
}
