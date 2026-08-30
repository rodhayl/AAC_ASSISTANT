import type { FormEvent } from 'react';
import { Mic, Send, Square, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Smartbar } from '../board/Smartbar';
import type { BoardSymbol } from '../../types';
import { Button } from '../ui/button';
import { IconButton } from '../ui/icon-button';

const inputToSymbols = (text: string, language: string): BoardSymbol[] => {
  if (!text.trim()) return [];

  return text.trim().split(/\s+/).map((word, index) => ({
    id: index,
    symbol_id: 0,
    position_x: 0,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: {
      id: 0,
      label: word,
      category: 'unknown',
      language,
      is_builtin: false,
      created_at: '',
    },
  }));
};

interface LearningInputRowProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  voiceEnabled: boolean;
  isRecording: boolean;
  hasRecording: boolean;
  isLoading: boolean;
  isStartingSession: boolean;
  boardId?: number | null;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  sendRecording: () => Promise<void>;
  discardRecording: () => void;
}

export function LearningInputRow({
  input,
  onInputChange,
  onSubmit,
  voiceEnabled,
  isRecording,
  hasRecording,
  isLoading,
  isStartingSession,
  boardId,
  startRecording,
  stopRecording,
  sendRecording,
  discardRecording,
}: LearningInputRowProps) {
  const { t, i18n } = useTranslation('learning');
  const currentLanguage = i18n.language?.split('-')[0] || 'en';

  return (
    <div className="p-4 border-t border-border bg-background">
      <div className="mb-3">
        <Smartbar
          currentSentence={inputToSymbols(input, currentLanguage)}
          onSelectSymbol={(symbol) => {
            const label = symbol.custom_text || symbol.symbol.label;
            onInputChange(
              `${input}${input.endsWith(' ') || input === '' ? '' : ' '}${label} `,
            );
          }}
          boardId={boardId ?? null}
        />
      </div>

      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          id="learning-text-input"
          name="learning_text_input"
          type="text"
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder={t('typeAnswer')}
          className="flex-1 p-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand bg-surface text-foreground"
          disabled={isLoading || isRecording || isStartingSession}
        />

        {voiceEnabled && (
          <>
            {isRecording ? (
              <IconButton
                label={t('stopRecordingLabel')}
                title={t('stopReview')}
                onClick={stopRecording}
                variant="default"
                className="p-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors animate-pulse size-auto"
              >
                <Square className="w-5 h-5" />
              </IconButton>
            ) : hasRecording ? (
              <>
                <IconButton
                  label={t('sendRecordingLabel')}
                  title={t('sendRecording')}
                  onClick={sendRecording}
                  variant="accent"
                  size="icon"
                  disabled={isLoading}
                >
                  <Send />
                </IconButton>
                <IconButton
                  label={t('discardRecordingLabel')}
                  title={t('discardRecording')}
                  onClick={discardRecording}
                  disabled={isLoading}
                  className="p-2 bg-muted text-muted-foreground rounded-lg hover:bg-surface-hover transition-colors size-auto"
                >
                  <Trash2 className="w-5 h-5" />
                </IconButton>
                {isLoading && (
                  <div className="flex items-center ml-2 text-xs text-muted-foreground">
                    <div className="w-2 h-2 mr-2 rounded-full bg-brand/100 animate-pulse" />
                    <span>{t('transcribing')}</span>
                  </div>
                )}
              </>
            ) : (
              <IconButton
                label={t('startRecordingLabel')}
                title={t('startRecording')}
                onClick={startRecording}
                disabled={isLoading || isStartingSession}
                className="p-2 bg-muted text-muted-foreground rounded-lg hover:bg-surface-hover transition-colors size-auto"
              >
                <Mic className="w-5 h-5" />
              </IconButton>
            )}
          </>
        )}

        <Button
          type="submit"
          variant="accent"
          size="icon"
          disabled={isLoading || isRecording || (!input.trim() && !isRecording) || isStartingSession}
          aria-label={t('sendMessage')}
        >
          <Send />
        </Button>
      </form>
    </div>
  );
}
