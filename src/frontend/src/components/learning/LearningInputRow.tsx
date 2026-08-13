import type { FormEvent } from 'react';
import { Mic, Send, Square, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Smartbar } from '../board/Smartbar';
import type { BoardSymbol } from '../../types';

const inputToSymbols = (text: string): BoardSymbol[] => {
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
      language: 'en',
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
  const { t } = useTranslation('learning');

  return (
    <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
      <div className="mb-3">
        <Smartbar
          currentSentence={inputToSymbols(input)}
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
          className="flex-1 p-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          disabled={isLoading || isRecording || isStartingSession}
        />

        {voiceEnabled && (
          <>
            {isRecording ? (
              <button
                type="button"
                onClick={stopRecording}
                className="p-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors animate-pulse"
                title={t('stopReview')}
                aria-label="Stop recording"
              >
                <Square className="w-5 h-5" />
              </button>
            ) : hasRecording ? (
              <>
                <button
                  type="button"
                  onClick={sendRecording}
                  className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                  title={t('sendRecording')}
                  aria-label="Send recording"
                  disabled={isLoading}
                >
                  <Send className="w-5 h-5" />
                </button>
                <button
                  type="button"
                  onClick={discardRecording}
                  className="p-2 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                  title={t('discardRecording')}
                  aria-label="Discard recording"
                  disabled={isLoading}
                >
                  <Trash2 className="w-5 h-5" />
                </button>
                {isLoading && (
                  <div className="flex items-center ml-2 text-xs text-gray-500 dark:text-gray-400">
                    <div className="w-2 h-2 mr-2 rounded-full bg-indigo-500 animate-pulse" />
                    <span>{t('transcribing')}</span>
                  </div>
                )}
              </>
            ) : (
              <button
                type="button"
                onClick={startRecording}
                className="p-2 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                title={t('startRecording')}
                aria-label="Start recording"
                disabled={isLoading || isStartingSession}
              >
                <Mic className="w-5 h-5" />
              </button>
            )}
          </>
        )}

        <button
          type="submit"
          disabled={isLoading || (!input.trim() && !isRecording) || isStartingSession}
          className="p-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50"
          aria-label={t('sendMessage')}
        >
          <Send className="w-5 h-5" />
        </button>
      </form>
    </div>
  );
}
