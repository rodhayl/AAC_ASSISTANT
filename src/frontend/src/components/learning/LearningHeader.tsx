import { Cloud, Cpu, Grid as GridIcon, HelpCircle, Sparkles, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { DifficultyOverride } from '../../store/learningStore';

interface LearningHeaderProps {
  showHistory: boolean;
  onToggleHistory: () => void;
  symbolView: boolean;
  onToggleSymbolView: () => void;
  selectedModeKey: string;
  onModeChange: (modeKey: string) => void;
  availableModes: Array<{ id: number; name: string; key: string; description: string }>;
  difficultyOverride: DifficultyOverride;
  onDifficultyChange: (difficulty: DifficultyOverride) => void;
  providerInUse?: 'ollama' | 'openrouter' | 'lmstudio';
  providerNotice: string | null;
  voiceEnabled: boolean;
  onToggleVoice: () => void;
  onNewQuestion: () => void;
  canAskQuestion: boolean;
}

export function LearningHeader({
  showHistory,
  onToggleHistory,
  symbolView,
  onToggleSymbolView,
  selectedModeKey,
  onModeChange,
  availableModes,
  difficultyOverride,
  onDifficultyChange,
  providerInUse,
  providerNotice,
  voiceEnabled,
  onToggleVoice,
  onNewQuestion,
  canAskQuestion,
}: LearningHeaderProps) {
  const { t } = useTranslation('learning');

  return (
    <div className="mb-6 flex justify-between items-start">
      <div className="flex items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center">
            <Sparkles className="w-6 h-6 text-indigo-600 dark:text-indigo-400 mr-2" />
            {t('title')}
          </h1>
          <p className="text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onToggleHistory}
            className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors text-sm font-medium"
          >
            {showHistory ? t('hideHistory', 'Hide History') : t('showHistory')}
          </button>
          <button
            onClick={onToggleSymbolView}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              symbolView
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
            title={t('toggleSymbolView', 'Toggle symbol-first view')}
          >
            <GridIcon className="w-4 h-4 inline-block mr-2" />
            {symbolView ? t('textChat') : t('symbolFirst')}
          </button>
          <button
            onClick={onNewQuestion}
            disabled={!canAskQuestion}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors flex items-center gap-1.5"
            title={t('newQuestionTitle', 'Get a new question')}
          >
            <HelpCircle className="w-4 h-4" />
            {t('newQuestion', 'New question')}
          </button>
          <div className="flex items-center gap-2 border-l border-gray-200 dark:border-gray-600 pl-3 ml-1">
            <label htmlFor="learning-mode" className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t('modeLabel', 'Mode')}:
            </label>
            <select
              id="learning-mode"
              name="learning_mode"
              value={selectedModeKey}
              onChange={(event) => onModeChange(event.target.value)}
              className="px-2 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-700 border-none text-sm text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500"
            >
              {availableModes.map((mode) => (
                <option key={mode.key} value={mode.key}>{mode.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2 border-l border-gray-200 dark:border-gray-600 pl-3 ml-1">
            <label htmlFor="learning-difficulty" className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t('difficultyLabel', 'Difficulty')}:
            </label>
            <select
              id="learning-difficulty"
              name="learning_difficulty"
              value={difficultyOverride}
              onChange={(event) => onDifficultyChange(event.target.value as DifficultyOverride)}
              className="px-2 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-700 border-none text-sm text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500"
              title={t('difficultyHelp', 'Choose a fixed level or let the AI adapt')}
            >
              <option value="adaptive">{t('difficulty.adaptive', 'Adaptive')}</option>
              <option value="basic">{t('difficulty.basic', 'Basic')}</option>
              <option value="intermediate">{t('difficulty.intermediate', 'Intermediate')}</option>
              <option value="advanced">{t('difficulty.advanced', 'Advanced')}</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {providerInUse && (() => {
          const label =
            providerInUse === 'openrouter'
              ? 'OpenRouter'
              : providerInUse === 'lmstudio'
                ? 'LM Studio'
                : 'Ollama';
          const isCloud = providerInUse === 'openrouter';
          return (
            <span
              className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border ${
                isCloud
                  ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                  : 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800'
              }`}
              title={t('currentProvider', 'Current AI provider')}
            >
              {isCloud ? <Cloud className="w-4 h-4" /> : <Cpu className="w-4 h-4" />}
              <span>{t('aiProviderLabel', 'AI: {{provider}}', { provider: label })}</span>
            </span>
          );
        })()}
        {providerNotice && (
          <div
            className="px-3 py-1 rounded-md text-xs bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
            role="status"
          >
            {providerNotice}
          </div>
        )}
        <button
          onClick={onToggleVoice}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
            voiceEnabled
              ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 hover:bg-indigo-200 dark:hover:bg-indigo-900/50'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
          }`}
          title={voiceEnabled ? t('disableVoice', 'Disable voice input') : t('enableVoice', 'Enable voice input')}
        >
          {voiceEnabled ? (
            <>
              <Volume2 className="w-5 h-5" />
              <span className="text-sm font-medium">{t('voiceOn')}</span>
            </>
          ) : (
            <>
              <VolumeX className="w-5 h-5" />
              <span className="text-sm font-medium">{t('voiceOff', 'Voice Off')}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
