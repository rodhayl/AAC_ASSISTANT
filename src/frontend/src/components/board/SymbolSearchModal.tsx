import React, { useState, useEffect, useRef } from 'react';
import { isAxiosError } from 'axios';
import { X, Search, Loader2, Filter, Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';
import { walkPages } from '../../lib/pagination';
import { SymbolCard } from './SymbolCard';
import type { BoardSymbol, Symbol } from '../../types';
import { Button } from '../ui/button';
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '../ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

interface SymbolSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSymbol: (symbol: BoardSymbol) => void;
}

// The backend caps a single /boards/symbols request at `limit` (max 1000); a
// single hardcoded 100-item page silently truncated larger result sets with no
// way to reach the rest (same defect class already fixed in SymbolPicker,
// rosters and history with walkPages). Walking pages keeps the whole match
// set reachable; walkPages stops on the first short page and hard-caps the
// walk so a backend that never shrinks its pages cannot loop forever.
const SEARCH_PAGE_SIZE = 1000;

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

const LANGUAGES = [
  { code: 'es' },
  { code: 'en' },
  { code: 'all' },
];


export function SymbolSearchModal({ isOpen, onClose, onSelectSymbol }: SymbolSearchModalProps) {
  const { t, i18n } = useTranslation('boards');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Symbol[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [category, setCategory] = useState<string>('');
  const [selectedLanguage, setSelectedLanguage] = useState<string>('');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchController = useRef<AbortController | null>(null);
  const searchGeneration = useRef(0);

  useEffect(() => {
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
      searchController.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!isOpen) {
      searchGeneration.current += 1;
      if (searchTimer.current) {
        clearTimeout(searchTimer.current);
        searchTimer.current = null;
      }
      searchController.current?.abort();
      searchController.current = null;
      setIsLoading(false);
      setResults([]);
      return;
    }

    // Default to current language, but allow switching
    const currentLang = i18n.language?.split('-')[0] || 'es';
    setSelectedLanguage(currentLang);
  }, [isOpen, i18n.language]);

  const handleSearch = async (
    e?: React.FormEvent,
    queryOverride?: string,
    filters?: { category?: string; language?: string },
  ) => {
    e?.preventDefault();
    const searchQuery = queryOverride ?? query;
    // Filter changes arrive with the new value explicitly: setState has not
    // re-rendered yet when the debounced callback fires, so reading the state
    // closure would search with the stale filter.
    const searchCategory = filters?.category ?? category;
    const searchLanguage = filters?.language ?? selectedLanguage;
    const generation = ++searchGeneration.current;
    if (searchTimer.current) {
      clearTimeout(searchTimer.current);
      searchTimer.current = null;
    }
    searchController.current?.abort();

    // Allow empty query if category is selected
    if (!searchQuery.trim() && !searchCategory) {
      setResults([]);
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    searchController.current = controller;
    setIsLoading(true);
    try {
      // Use server-side search and walk every matching page (see
      // SEARCH_PAGE_SIZE). walkPages validates each page with Array.isArray so
      // a malformed payload can never be rendered as a result list.
      const params: Record<string, string | number> = {
        search: searchQuery // Pass search query to backend
      };

      if (searchLanguage && searchLanguage !== 'all') {
        params.language = searchLanguage;
      }

      if (searchCategory && searchCategory !== 'all') {
        params.category = searchCategory;
      }

      const symbols = await walkPages<Symbol>({
        pageSize: SEARCH_PAGE_SIZE,
        fetchPage: async (skip) => {
          const res = await api.get('/boards/symbols', {
            params: { ...params, skip, limit: SEARCH_PAGE_SIZE },
            signal: controller.signal,
          });
          return res.data;
        },
        isCancelled: () => generation !== searchGeneration.current,
      });

      if (generation === searchGeneration.current) {
        setResults(symbols);
      }
    } catch (error) {
      const isCancellation = isAxiosError(error) && error.code === 'ERR_CANCELED';
      if (generation === searchGeneration.current && !isCancellation) {
        console.error("Search failed", error);
        setResults([]);
      }
    } finally {
      if (generation === searchGeneration.current) {
        setIsLoading(false);
        if (searchController.current === controller) searchController.current = null;
      }
    }
  };

  if (!isOpen) return null;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        className="max-w-2xl h-[85vh] flex flex-col overflow-hidden p-0"
      >
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Search className="w-5 h-5 text-brand" />
            <DialogTitle className="text-lg font-semibold text-foreground">
              {t('symbolSearch')}
            </DialogTitle>
          </div>
          <button onClick={onClose} aria-label={t('close')} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 border-b border-border bg-background space-y-3">
          <form onSubmit={handleSearch} className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => {
                const nextQuery = e.target.value;
                setQuery(nextQuery);
                if (searchTimer.current) {
                  clearTimeout(searchTimer.current);
                  searchTimer.current = null;
                }
                if (!nextQuery.trim() && !category) {
                  searchGeneration.current += 1;
                  searchController.current?.abort();
                  searchController.current = null;
                  setResults([]);
                  setIsLoading(false);
                  return;
                }
                searchTimer.current = setTimeout(() => {
                  searchTimer.current = null;
                  void handleSearch(undefined, nextQuery);
                }, 200);
              }}
              placeholder={t('symbolSearchPlaceholder')}
              className="flex-1 px-4 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
              autoFocus
            />
            <Button type="submit" disabled={isLoading || (!query.trim() && !category)}  >
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : t('search')}
            </Button>
          </form>

          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Filter className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground pointer-events-none z-10" />
              <Select
                value={category === '' ? 'all' : category}
                onValueChange={(next) => {
                  // Base UI Select cannot commit an empty-string item value,
                  // so the "all" option uses a sentinel that maps back to the
                  // empty filter state the API layer expects.
                  const mapped = next === 'all' || next == null ? '' : next;
                  setCategory(mapped);
                  if (searchTimer.current) {
                    clearTimeout(searchTimer.current);
                    searchTimer.current = null;
                  }
                  searchTimer.current = setTimeout(() => {
                    searchTimer.current = null;
                    void handleSearch(undefined, query, { category: mapped });
                  }, 200);
                }}
                items={[
                  { value: 'all', label: t('allCategories') },
                  ...CATEGORIES.map((cat) => ({
                    value: cat,
                    label: t(`categories.${cat}`, cat.charAt(0).toUpperCase() + cat.slice(1)),
                  })),
                ]}
              >
                <SelectTrigger aria-label={t('allCategories')} className="w-full pl-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('allCategories')}</SelectItem>
                  {CATEGORIES.map(cat => (
                    <SelectItem key={cat} value={cat}>
                      {t(`categories.${cat}`, cat.charAt(0).toUpperCase() + cat.slice(1))}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex-1 relative">
              <Globe className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground pointer-events-none z-10" />
              <Select
                value={selectedLanguage}
                onValueChange={(next) => {
                  const language = next ?? 'all';
                  setSelectedLanguage(language);
                  if (searchTimer.current) {
                    clearTimeout(searchTimer.current);
                    searchTimer.current = null;
                  }
                  searchTimer.current = setTimeout(() => {
                    searchTimer.current = null;
                    void handleSearch(undefined, query, { language });
                  }, 200);
                }}
                items={LANGUAGES.map((lang) => ({
                  value: lang.code,
                  label: lang.code === 'all'
                    ? t('allLanguages')
                    : t(`languages.${lang.code}`, lang.code.toUpperCase()),
                }))}
              >
                <SelectTrigger aria-label={t('allLanguages')} className="w-full pl-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LANGUAGES.map(lang => (
                    <SelectItem key={lang.code} value={lang.code}>
                      {lang.code === 'all'
                        ? t('allLanguages')
                        : t(`languages.${lang.code}`, lang.code.toUpperCase())}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 bg-muted  rounded-b-xl">
          {results.length === 0 && !isLoading && query && (
            <div className="text-center text-muted-foreground mt-10">
              {t('noResults')}
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
      </DialogContent>
    </Dialog>
  );
}
