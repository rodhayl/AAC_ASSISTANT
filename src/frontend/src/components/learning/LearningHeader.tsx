import { Cloud, Cpu, Grid as GridIcon, HelpCircle, Sparkles, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import type { DifficultyOverride, LLMProviderId } from '../../store/learningStore';

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
  providerInUse?: LLMProviderId;
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
    <div className="mb-6 flex flex-col gap-4">
      <div className="min-w-0 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 shrink-0">
          <h1 className="text-2xl font-bold text-foreground flex items-center">
            <Sparkles className="w-6 h-6 text-brand mr-2" />
            {t('title')}
          </h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <button
            onClick={onToggleHistory}
            className="shrink-0 px-4 py-2 bg-muted text-foreground rounded-lg hover:bg-surface-hover transition-colors text-sm font-medium"
          >
            {showHistory ? t('hideHistory') : t('showHistory')}
          </button>
          <button
            onClick={onToggleSymbolView}
            className={`shrink-0 px-4 py-2 rounded-lg text-sm font-medium ${
              symbolView
                ? 'bg-brand text-white'
                : 'bg-muted text-foreground hover:bg-surface-hover'
            }`}
            title={t('toggleSymbolView')}
          >
            <GridIcon className="w-4 h-4 inline-block mr-2" />
            {symbolView ? t('textChat') : t('symbolFirst')}
          </button>
          <Button
            variant="accent"
            size="sm"
            onClick={onNewQuestion}
            disabled={!canAskQuestion}
            title={t('newQuestionTitle')}
          >
            <HelpCircle />
            {t('newQuestion')}
          </Button>
          <div className="flex items-center gap-2 border-l border-border pl-3 ml-1 max-sm:border-l-0 max-sm:pl-0">
            <label htmlFor="learning-mode" className="text-xs font-medium text-muted-foreground">
              {t('modeLabel')}:
            </label>
            <select
              id="learning-mode"
              name="learning_mode"
              value={selectedModeKey}
              onChange={(event) => onModeChange(event.target.value)}
              className="px-2 py-1.5 rounded-lg bg-muted border-none text-sm text-foreground focus:ring-2 focus:ring-brand"
            >
              {availableModes.map((mode) => (
                <option key={mode.key} value={mode.key}>{mode.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2 border-l border-border pl-3 ml-1 max-sm:border-l-0 max-sm:pl-0">
            <label htmlFor="learning-difficulty" className="text-xs font-medium text-muted-foreground">
              {t('difficultyLabel')}:
            </label>
            <select
              id="learning-difficulty"
              name="learning_difficulty"
              value={difficultyOverride}
              onChange={(event) => onDifficultyChange(event.target.value as DifficultyOverride)}
              className="px-2 py-1.5 rounded-lg bg-muted border-none text-sm text-foreground focus:ring-2 focus:ring-brand"
              title={t('difficultyHelp')}
            >
              <option value="adaptive">{t('difficulty.adaptive')}</option>
              <option value="basic">{t('difficulty.basic')}</option>
              <option value="intermediate">{t('difficulty.intermediate')}</option>
              <option value="advanced">{t('difficulty.advanced')}</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-3 xl:justify-end">
        {providerInUse && (() => {
          const label =
            providerInUse === 'openrouter'
              ? 'OpenRouter'
              : providerInUse === 'lmstudio'
                ? 'LM Studio'
                : providerInUse === 'groq'
                  ? 'Groq'
                  : 'Ollama';
          const isCloud = providerInUse === 'openrouter' || providerInUse === 'groq';
          return (
            <span
              className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border ${
                isCloud
                  ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                  : 'bg-brand/10 text-brand border-brand/20'
              }`}
              title={t('currentProvider')}
            >
              {isCloud ? <Cloud className="w-4 h-4" /> : <Cpu className="w-4 h-4" />}
              <span>{t('aiProviderLabel', { provider: label })}</span>
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
          className={`flex shrink-0 items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
            voiceEnabled
              ? 'bg-brand/10 text-brand hover:bg-brand/20'
              : 'bg-muted text-muted-foreground hover:bg-surface-hover'
          }`}
          title={voiceEnabled ? t('disableVoice') : t('enableVoice')}
        >
          {voiceEnabled ? (
            <>
              <Volume2 className="w-5 h-5" />
              <span className="text-sm font-medium">{t('voiceOn')}</span>
            </>
          ) : (
            <>
              <VolumeX className="w-5 h-5" />
              <span className="text-sm font-medium">{t('voiceOff')}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
