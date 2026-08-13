import { Lock, Play, Save, Settings, Sparkles, Trash2, Unlock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { BoardPlayabilityStatus } from '../../pages/boardEditorUtils';

interface BoardEditorToolbarProps {
  boardName: string;
  showSuggestions: boolean;
  aiLoading: boolean;
  status: BoardPlayabilityStatus;
  gridPreset: string;
  hasChanges: boolean;
  hasSymbols: boolean;
  isBusy: boolean;
  onLoadSuggestions: () => void;
  onSpeakMode: () => void;
  onOpenSettings: () => void;
  onGridChange: (preset: string) => void;
  onSave: () => void;
  onClear: () => void;
}

export function BoardEditorToolbar({
  boardName,
  showSuggestions,
  aiLoading,
  status,
  gridPreset,
  hasChanges,
  hasSymbols,
  isBusy,
  onLoadSuggestions,
  onSpeakMode,
  onOpenSettings,
  onGridChange,
  onSave,
  onClear,
}: BoardEditorToolbarProps) {
  const { t } = useTranslation('boards');

  return (
    <div className="flex justify-between items-center mb-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{boardName}</h1>
        <p className="text-gray-500 dark:text-gray-400">{t('editBoardSubtitle')}</p>
      </div>
      <div className="flex space-x-3 items-center">
        <div className={`hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full border ${status.playable
          ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400'
          : 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400'
          }`}>
          {status.playable ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
          <span className="text-xs font-bold uppercase tracking-wider">
            {status.playable
              ? t('boardReady', 'Board Ready')
              : t('boardIncomplete', '{{count}}/{{total}} Symbols', {
                count: status.count,
                total: status.threshold,
              })}
          </span>
          {!status.playable && (
            <div className="w-24 h-2 bg-amber-200 dark:bg-amber-900/50 rounded-full overflow-hidden ml-2 border border-amber-300 dark:border-amber-800 shadow-inner">
              <div
                className="h-full bg-gradient-to-r from-amber-400 to-amber-600 transition-all duration-700 ease-out shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                style={{ width: `${status.progress}%` }}
              />
            </div>
          )}
        </div>

        {showSuggestions && (
          <button
            onClick={onLoadSuggestions}
            disabled={aiLoading}
            className="inline-flex items-center px-4 py-2 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100 disabled:opacity-50"
          >
            <Sparkles className={`w-4 h-4 mr-2 ${aiLoading ? 'animate-spin' : ''}`} />
            {aiLoading ? t('fetchingIdeas') : t('getSuggestions')}
          </button>
        )}
        <button
          onClick={onSpeakMode}
          className="inline-flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 shadow-sm transition-colors"
          title={t('enterSpeakMode')}
        >
          <Play className="w-4 h-4 mr-2 fill-current" />
          {t('speakMode')}
        </button>
        <button
          onClick={onOpenSettings}
          className="p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          aria-label={t('boardSettings')}
        >
          <Settings className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2">
          <label htmlFor="board-layout" className="text-sm text-gray-600 dark:text-gray-400">{t('layout')}</label>
          <select
            id="board-layout"
            name="board_layout"
            value={gridPreset}
            onChange={(event) => onGridChange(event.target.value)}
            className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          >
            <option value="2x2">2x2</option>
            <option value="3x3">3x3</option>
            <option value="4x4">4x4</option>
            <option value="2x6">2x6</option>
            <option value="4x5">4x5</option>
          </select>
        </div>
        <button
          onClick={onSave}
          disabled={!hasChanges}
          className={`flex items-center px-4 py-2 rounded-lg ${hasChanges
            ? 'bg-indigo-600 text-white hover:bg-indigo-700'
            : 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
            }`}
        >
          <Save className="w-4 h-4 mr-2" />
          {hasChanges ? t('saveLayout') : t('noChanges')}
        </button>
        <button
          onClick={onClear}
          disabled={isBusy || !hasSymbols}
          className="flex items-center px-4 py-2 rounded-lg bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 disabled:opacity-50"
          title={t('clearBoardTitle')}
        >
          <Trash2 className="w-4 h-4 mr-2" />
          {t('clearBoard')}
        </button>
      </div>
    </div>
  );
}
