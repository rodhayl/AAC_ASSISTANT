import { Lock, Play, Save, Settings, Sparkles, Trash2, Unlock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { BoardPlayabilityStatus } from '../../pages/boardEditorUtils';
import { Button } from '../ui/button';

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

const GRID_PRESETS = ['2x2', '3x3', '4x4', '2x6', '4x5'];

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
        <h1 className="text-2xl font-bold text-foreground">{boardName}</h1>
        <p className="text-muted-foreground">{t('editBoardSubtitle')}</p>
      </div>
      <div className="flex space-x-3 items-center">
        <div className={`hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full border ${status.playable
          ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400'
          : 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400'
          }`}>
          {status.playable ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
          <span className="text-xs font-bold uppercase tracking-wider">
            {status.playable
              ? t('boardReady')
              : t('boardIncomplete', {
                count: status.count,
                total: status.threshold,
              })}
          </span>
          {!status.playable && (
            <div className="w-24 h-2 bg-amber-200 dark:bg-amber-900/50 rounded-full overflow-hidden ml-2 border border-amber-300 dark:border-amber-800 shadow-inner">
              <div
                className="h-full bg-gradient-to-r from-amber-400 to-amber-600 transition-all duration-700 ease-out shadow-sm"
                style={{ width: `${status.progress}%` }}
              />
            </div>
          )}
        </div>

        {showSuggestions && (
          <button
            onClick={onLoadSuggestions}
            disabled={aiLoading}
            className="inline-flex items-center px-4 py-2 bg-brand/10 text-brand border border-brand/30 rounded-lg hover:bg-brand/10 disabled:opacity-50"
          >
            <Sparkles className={`w-4 h-4 mr-2 ${aiLoading ? 'animate-spin' : ''}`} />
            {aiLoading ? t('fetchingIdeas') : t('getSuggestions')}
          </button>
        )}
        <Button
          variant="success"
          onClick={onSpeakMode}
          className="shadow-sm"
          title={t('enterSpeakMode')}
        >
          <Play className="fill-current" />
          {t('speakMode')}
        </Button>
        <button
          onClick={onOpenSettings}
          className="p-2 text-muted-foreground hover:bg-surface-hover rounded-lg"
          aria-label={t('boardSettings')}
        >
          <Settings className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2">
          <label htmlFor="board-layout" className="text-sm text-muted-foreground">{t('layout')}</label>
          <select
            id="board-layout"
            name="board_layout"
            value={gridPreset}
            onChange={(event) => onGridChange(event.target.value)}
            className="px-2 py-1 border border-border rounded-md text-sm bg-surface text-foreground"
          >
            <option value="2x2">{t('grid2x2')}</option>
            <option value="3x3">{t('grid3x3')}</option>
            <option value="4x4">{t('grid4x4')}</option>
            <option value="2x6">{t('grid2x6')}</option>
            <option value="4x5">{t('grid4x5')}</option>
            {!GRID_PRESETS.includes(gridPreset) && (
              <option value={gridPreset}>{gridPreset}</option>
            )}
          </select>
        </div>
        <button
          onClick={onSave}
          disabled={!hasChanges}
          className={`flex items-center px-4 py-2 rounded-lg ${hasChanges
            ? 'bg-brand text-white hover:bg-brand/80'
            : 'bg-muted text-muted-foreground cursor-not-allowed'
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
