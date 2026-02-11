import React, { useState, useEffect } from 'react';
import { X, Search, Loader2, Filter, Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';
import { SymbolCard } from './SymbolCard';
import type { BoardSymbol, Symbol } from '../../types';

interface SymbolSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSymbol: (symbol: BoardSymbol) => void;
}

const CATEGORIES = [
  'general',
  'people',
  'actions',
  'objects',
  'places',
  'animals',
  'emotions',
  'food',
  'social',
  'education',
  'medical'
];

const LANGUAGES_RAW = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
  { code: 'all', label: 'All' }
];

const LANGUAGES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
  { code: 'all', label: 'All' }
];

void LANGUAGES_RAW;

export function SymbolSearchModal({ isOpen, onClose, onSelectSymbol }: SymbolSearchModalProps) {
  const { t, i18n } = useTranslation('boards');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Symbol[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [category, setCategory] = useState<string>('');
  const [selectedLanguage, setSelectedLanguage] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      // Default to current language, but allow switching
      const currentLang = i18n.language?.split('-')[0] || 'es';
      setSelectedLanguage(currentLang);
    }
  }, [isOpen, i18n.language]);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    // Allow empty query if category is selected
    if (!query.trim() && !category) return;

    setIsLoading(true);
    try {
      // Use server-side search
      const params: Record<string, string | number> = {
        limit: 100,
        search: query // Pass search query to backend
      };

      if (selectedLanguage && selectedLanguage !== 'all') {
        params.language = selectedLanguage;
      }

      if (category && category !== 'all') {
        params.category = category;
      }

      const res = await api.get('/boards/symbols', { params });

      const results = res.data || [];
      setResults(results);
    } catch (error) {
      console.error("Search failed", error);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-900/90 backdrop-blur-xl border border-border dark:border-white/10 rounded-xl shadow-xl w-full max-w-2xl h-[85vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Search className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {t('symbolSearch', 'Find Symbols')}
            </h2>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 border-b border-border dark:border-white/5 bg-gray-50 dark:bg-white/5 space-y-3">
          <form onSubmit={handleSearch} className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('symbolSearchPlaceholder', 'Search for a symbol...')}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              autoFocus
            />
            <button
              type="submit"
              disabled={isLoading || (!query.trim() && !category)}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : t('search', 'Search')}
            </button>
          </form>

          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Filter className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400" />
              <select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  // Optional: auto-trigger search on filter change
                  // setTimeout(() => handleSearch(), 0);
                }}
                className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 appearance-none"
              >
                <option value="">{t('allCategories', 'All Categories')}</option>
                {CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>
                    {t(`categories.${cat}`, cat.charAt(0).toUpperCase() + cat.slice(1))}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex-1 relative">
              <Globe className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400" />
              <select
                value={selectedLanguage}
                onChange={(e) => {
                  setSelectedLanguage(e.target.value);
                }}
                className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 appearance-none"
              >
                {LANGUAGES.map(lang => (
                  <option key={lang.code} value={lang.code}>
                    {lang.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 bg-gray-100 dark:bg-gray-900/50">
          {results.length === 0 && !isLoading && query && (
            <div className="text-center text-gray-500 dark:text-gray-400 mt-10">
              {t('noResults', 'No symbols found.')}
            </div>
          )}

          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3">
            {results.map((symbol) => {
              const tempSymbol: BoardSymbol = {
                id: -symbol.id,
                symbol_id: symbol.id,
                position_x: 0,
                position_y: 0,
                size: 1,
                is_visible: true,
                custom_text: symbol.label,
                symbol: {
                  ...symbol,
                  is_builtin: false,
                  is_in_use: true,
                  created_at: new Date().toISOString()
                }
              };

              return (
                <div key={symbol.id} className="aspect-square">
                  <SymbolCard
                    boardSymbol={tempSymbol}
                    onClick={() => {
                      onSelectSymbol(tempSymbol);
                      onClose();
                    }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
