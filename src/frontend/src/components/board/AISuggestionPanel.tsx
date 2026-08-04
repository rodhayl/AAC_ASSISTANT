import { ArrowLeftRight, PlusCircle, RefreshCcw, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { BoardPosition } from '../../hooks/useBoardCollab';

export type AISuggestion = {
  label: string;
  symbol_key?: string;
  color?: string;
  description?: string;
};

interface AISuggestionPanelProps {
  suggestions: AISuggestion[];
  aiError: string | null;
  aiLoading: boolean;
  applyAllLoading: boolean;
  applyId: string | null;
  isFull: boolean;
  rows: number;
  cols: number;
  refinePrompt: string;
  selectedPosition: BoardPosition | null;
  onApplyAll: () => void;
  onRefresh: () => void;
  onRefine: () => void;
  onRegenerate: () => void;
  onRefinePromptChange: (value: string) => void;
  onApply: (item: AISuggestion, position?: BoardPosition) => void;
}

export function AISuggestionPanel({
  suggestions,
  aiError,
  aiLoading,
  applyAllLoading,
  applyId,
  isFull,
  rows,
  cols,
  refinePrompt,
  selectedPosition,
  onApplyAll,
  onRefresh,
  onRefine,
  onRegenerate,
  onRefinePromptChange,
  onApply,
}: AISuggestionPanelProps) {
  const { t } = useTranslation('boards');

  return (
    <div className="bg-white dark:bg-gray-800 border border-indigo-100 dark:border-indigo-800 rounded-xl p-4 shadow-sm mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-600" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{t('aiSuggestionsTitle')}</h3>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onApplyAll}
            disabled={aiLoading || applyAllLoading || !suggestions.length}
            className="flex items-center text-sm px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            title={t('addAllTitle')}
          >
            <PlusCircle className="w-4 h-4 mr-1" />
            {applyAllLoading ? t('addingAll') : t('addAll')}
          </button>
          <button
            onClick={onRefresh}
            className="flex items-center text-sm text-indigo-600 hover:text-indigo-700"
            disabled={aiLoading}
          >
            <RefreshCcw className={`w-4 h-4 mr-1 ${aiLoading ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </button>
        </div>
      </div>
      {isFull && (
        <div className="mb-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          {t('boardFullWarning', { rows, cols })}
        </div>
      )}
      <div className="grid gap-2 mb-3 md:grid-cols-[1fr_auto_auto] md:items-center">
        <div className="md:col-span-1">
          <label className="block text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">
            {t('refineLabel')}
          </label>
          <input
            type="text"
            value={refinePrompt}
            onChange={(event) => onRefinePromptChange(event.target.value)}
            placeholder={t('refinePlaceholder')}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900/40 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
        <button
          onClick={onRefine}
          disabled={aiLoading}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-60"
        >
          {aiLoading ? t('refining') : t('sendRefinePrompt')}
        </button>
        <button
          onClick={onRegenerate}
          disabled={aiLoading}
          className="px-4 py-2 bg-white dark:bg-gray-900/60 border border-indigo-200 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-800 disabled:opacity-60"
          title={t('regenerateTitle')}
        >
          {aiLoading ? t('regenerating') : t('regenerateFullBoard')}
        </button>
      </div>
      {aiError && <div className="text-sm text-red-600 mb-2">{aiError}</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {suggestions.map((item) => (
          <div key={item.label} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-900/40 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-gray-900 dark:text-gray-100">{item.label}</div>
                {item.symbol_key && <div className="text-xs text-gray-500">{t('keyword', { key: item.symbol_key })}</div>}
              </div>
              {item.color && <span className="w-4 h-4 rounded-full border" style={{ background: item.color }} />}
            </div>
            {item.description && <div className="text-xs text-gray-500">{item.description}</div>}
            <button
              onClick={() => onApply(item)}
              disabled={applyId === item.label}
              className="inline-flex items-center justify-center px-3 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              <PlusCircle className="w-4 h-4 mr-1" />
              {applyId === item.label ? t('adding') : t('addToBoard')}
            </button>
            <button
              onClick={() => onApply(item, selectedPosition || undefined)}
              disabled={applyId === item.label || !selectedPosition}
              className="inline-flex items-center justify-center px-3 py-2 text-sm bg-white dark:bg-gray-900/60 border border-indigo-200 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-800 disabled:opacity-50"
              title={t('replaceTitle')}
            >
              <ArrowLeftRight className="w-4 h-4 mr-1" />
              {applyId === item.label ? t('replacing') : t('replaceAtSelected')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
