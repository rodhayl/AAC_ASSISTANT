import { Cloud, Cpu, Grid as GridIcon, Sparkles, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface LearningHeaderProps {
  showHistory: boolean;
  onToggleHistory: () => void;
  symbolView: boolean;
  onToggleSymbolView: () => void;
  selectedModeKey: string;
  onModeChange: (modeKey: string) => void;
  availableModes: Array<{ id: number; name: string; key: string; description: string }>;
  providerInUse?: 'ollama' | 'openrouter';
  providerNotice: string | null;
  voiceEnabled: boolean;
  onToggleVoice: () => void;
}

export function LearningHeader({
  showHistory,
  onToggleHistory,
  symbolView,
  onToggleSymbolView,
  selectedModeKey,
  onModeChange,
  availableModes,
  providerInUse,
  providerNotice,
  voiceEnabled,
  onToggleVoice,
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
            title="Toggle symbol-first view"
          >
            <GridIcon className="w-4 h-4 inline-block mr-2" />
            {symbolView ? t('textChat') : t('symbolFirst')}
          </button>
          <div className="flex items-center gap-2 border-l border-gray-200 dark:border-gray-600 pl-3 ml-1">
            <label htmlFor="learning-mode" className="text-xs font-medium text-gray-500 dark:text-gray-400">
              Mode:
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
        </div>
      </div>

      <div className="flex items-center gap-3">
        {providerInUse && (
          <span
            className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border ${
              providerInUse === 'openrouter'
                ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                : 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800'
            }`}
            title="Current AI provider"
          >
            {providerInUse === 'openrouter' ? <Cloud className="w-4 h-4" /> : <Cpu className="w-4 h-4" />}
            <span>AI: {providerInUse === 'openrouter' ? 'OpenRouter' : 'Ollama'}</span>
          </span>
        )}
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
              : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
          }`}
          title={voiceEnabled ? 'Disable voice input' : 'Enable voice input'}
        >
          {voiceEnabled ? (
            <>
              <Volume2 className="w-5 h-5" />
              <span className="text-sm font-medium">{t('voiceOn')}</span>
            </>
          ) : (
            <>
              <VolumeX className="w-5 h-5" />
              <span className="text-sm font-medium">Voice Off</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
