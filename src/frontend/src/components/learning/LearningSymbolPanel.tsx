import { useTranslation } from 'react-i18next';
import { Search, Volume2, X } from 'lucide-react';
import { SymbolImage } from '../common/SymbolImage';
import { glossSymbolUtterance } from '../../lib/gloss';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';
import { LEARNING_SYMBOL_CATEGORY_IDS } from '../../lib/symbolCategories';
import type { LearningSymbolItem } from '../../types';
import { Button } from '../ui/button';

import { SectionTitle } from '@/components/ui/SectionTitle';

export type { LearningSymbolItem } from '../../types';

interface LearningSymbolPanelProps {
  filteredSymbols: LearningSymbolItem[];
  coreWords: LearningSymbolItem[];
  symbolLoading: boolean;
  symbolSearch: string;
  onSearchChange: (value: string) => void;
  selectedCategory: string;
  onCategoryChange: (category: string) => void;
  symbolUtterance: LearningSymbolItem[];
  onAddSymbol: (symbol: LearningSymbolItem) => void;
  onRemoveSymbol: (index: number) => void;
  onClearSymbols: () => void;
  onSendSymbols: () => void;
  onSpeakSymbols: (text: string) => void;
  isLoading: boolean;
  isStartingSession: boolean;
}

export function LearningSymbolPanel({
  filteredSymbols,
  coreWords,
  symbolLoading,
  symbolSearch,
  onSearchChange,
  selectedCategory,
  onCategoryChange,
  symbolUtterance,
  onAddSymbol,
  onRemoveSymbol,
  onClearSymbols,
  onSendSymbols,
  onSpeakSymbols,
  isLoading,
  isStartingSession,
}: LearningSymbolPanelProps) {
  const { t } = useTranslation('learning');
  const categories = [
    { id: 'all', label: t('categories.all') },
    ...LEARNING_SYMBOL_CATEGORY_IDS.map((id) => ({
      id,
      label: t(`categories.${id}`),
    })),
  ];

  const categoryClasses = (category: string) => {
    const style = getCategoryStyle(category);
    return `${style.badgeBg} ${style.badgeText} ${style.border}`;
  };

  return (
    <div className="w-[450px] bg-surface rounded-xl shadow-sm border border-border flex flex-col overflow-hidden">
      <div className="p-4 border-b border-border">
        <SectionTitle as="h3">
          {t('symbolFirst')}
        </SectionTitle>

        {symbolUtterance.length > 0 && (
          <div className="mb-2 bg-muted border border-border rounded-lg p-3">
            <div className="text-sm font-semibold text-foreground mb-2">
              {t('utteranceBuilder')}
            </div>
            <div className="flex flex-wrap gap-2 mb-2">
              {symbolUtterance.map((symbol, index) => (
                <span
                  key={`${symbol.id}-${index}`}
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${categoryClasses(symbol.category)}`}
                >
                  {symbol.label}
                  <button
                    type="button"
                    onClick={() => onRemoveSymbol(index)}
                    className="hover:opacity-70 ml-1"
                    aria-label={t('removeSymbolLabel')}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => onSpeakSymbols(glossSymbolUtterance(symbolUtterance))}
                className="px-3 py-2 bg-muted text-foreground rounded-lg text-xs hover:bg-surface-hover flex items-center gap-1"
                disabled={symbolUtterance.length === 0}
                title={t('speakOnly')}
              >
                <Volume2 className="w-4 h-4" />
                {t('speakOnly')}
              </button>
              <Button type="button" onClick={onSendSymbols} className="text-xs" disabled={isLoading || symbolUtterance.length === 0 || isStartingSession} >
                {isStartingSession ? t('startingSession') : t('sendSymbols')}
              </Button>
              <button
                type="button"
                onClick={onClearSymbols}
                className="px-3 py-2 bg-muted text-foreground rounded-lg text-xs hover:bg-surface-hover"
                disabled={isLoading || isStartingSession}
              >
                {t('clear')}
              </button>
            </div>
          </div>
        )}

        <div className="mt-3 flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
            <input
              id="learning-symbol-search"
              name="learning_symbol_search"
              value={symbolSearch}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder={t('search')}
              className="w-full pl-9 pr-3 py-2 border border-border rounded-lg bg-surface text-foreground text-sm"
            />
          </div>
        </div>

        <div className="mt-3 flex gap-1 overflow-x-auto pb-2 scrollbar-hide">
          {categories.map((category) => (
            <button
              key={category.id}
              onClick={() => onCategoryChange(category.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                selectedCategory === category.id
                  ? 'bg-brand text-white'
                  : 'bg-muted text-muted-foreground hover:bg-surface-hover'
              }`}
            >
              {category.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-24 bg-background border-r border-border overflow-y-auto p-2 space-y-2">
          <div className="text-xs font-semibold text-muted-foreground uppercase mb-2 text-center">
            {t('categories.core')}
          </div>
          {coreWords.map((symbol) => (
            <button
              key={`core-${symbol.id}`}
              onClick={() => onAddSymbol(symbol)}
              className={`w-full p-2 rounded-lg border text-center text-xs font-medium hover:brightness-95 transition-all ${categoryClasses(symbol.category)}`}
            >
              {symbol.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-3 grid grid-cols-3 gap-2 content-start">
          {symbolLoading ? (
            <div className="col-span-3 text-center text-muted-foreground py-8">{t('loading')}</div>
          ) : filteredSymbols.length === 0 ? (
            <div className="col-span-3 text-center text-muted-foreground py-8">{t('noSymbols')}</div>
          ) : (
            filteredSymbols.map((symbol) => (
              <button
                key={symbol.id}
                onClick={() => onAddSymbol(symbol)}
                className="p-2 rounded-lg border border-border bg-background hover:border-brand text-center flex flex-col items-center h-24 justify-center"
                title={symbol.label}
              >
                {symbol.image_path ? (
                  <SymbolImage
                    imagePath={symbol.image_path}
                    alt={symbol.label}
                    className="w-10 h-10 object-contain mb-1"
                  />
                ) : (
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-1 ${categoryClasses(symbol.category)} bg-surface/20`}>
                    <span className="text-xs font-bold">{symbol.label.substring(0, 2).toUpperCase()}</span>
                  </div>
                )}
                <span className="text-xs font-medium text-foreground leading-tight line-clamp-2">
                  {symbol.label}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
