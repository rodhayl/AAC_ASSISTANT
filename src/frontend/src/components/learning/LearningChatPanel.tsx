import type { FormEvent } from 'react';
import { Bot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LearningInputRow } from './LearningInputRow';
import { LearningMessageList, type LearningMessage } from './LearningMessageList';
import type { LearningSessionResponse } from '../../types';

interface LearningChatPanelProps {
  messages: LearningMessage[];
  isLoading: boolean;
  error: string | null;
  isStartingSession: boolean;
  sessionStartError: string | null;
  currentSession: LearningSessionResponse | null;
  isAdmin: boolean;
  showAdminReasoning: boolean;
  onShowAdminReasoningChange: (value: boolean) => void;
  onStartSession: () => void;
  editingMessageIndex: number | null;
  onEditMessage: (index: number) => void;
  onUpdateSymbols: (symbols: Array<{
    id: number;
    label: string;
    image_path?: string;
    category?: string;
  }>) => Promise<void>;
  onCancelEdit: () => void;
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  voiceEnabled: boolean;
  isRecording: boolean;
  hasRecording: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  sendRecording: () => Promise<void>;
  discardRecording: () => void;
}

export function LearningChatPanel({
  messages,
  isLoading,
  error,
  isStartingSession,
  sessionStartError,
  currentSession,
  isAdmin,
  showAdminReasoning,
  onShowAdminReasoningChange,
  onStartSession,
  editingMessageIndex,
  onEditMessage,
  onUpdateSymbols,
  onCancelEdit,
  input,
  onInputChange,
  onSubmit,
  voiceEnabled,
  isRecording,
  hasRecording,
  startRecording,
  stopRecording,
  sendRecording,
  discardRecording,
}: LearningChatPanelProps) {
  const { t } = useTranslation('learning');

  return (
    <div className="flex-1 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-gray-900/50">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="font-semibold text-gray-900 dark:text-gray-100 text-sm">
              Learning Companion
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Practice questions, explanations, and conversational support
            </div>
          </div>
        </div>
        {isAdmin && (
          <label className="flex items-center gap-1 cursor-pointer select-none text-xs text-gray-500 dark:text-gray-400">
            <input
              id="show-admin-reasoning"
              name="show_admin_reasoning"
              type="checkbox"
              className="mr-1"
              checked={showAdminReasoning}
              onChange={(event) => onShowAdminReasoningChange(event.target.checked)}
            />
            <span>Show thinking</span>
          </label>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {isStartingSession && (
          <div className="flex justify-center items-center p-6 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg border border-indigo-200 dark:border-indigo-800">
            <div className="text-center">
              <div className="inline-flex items-center justify-center mb-3">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
              </div>
              <p className="text-indigo-700 dark:text-indigo-300 font-medium">
                {t('startingSession')}
              </p>
              <p className="text-indigo-600 dark:text-indigo-400 text-sm mt-1">{t('mayTake')}</p>
            </div>
          </div>
        )}

        {sessionStartError && (
          <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300">
            <p className="font-medium">{sessionStartError}</p>
          </div>
        )}

        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300">
            <p className="font-medium">Error: {error}</p>
          </div>
        )}

        {messages.length === 0 && !isLoading && !currentSession && !isStartingSession && (
          <div className="text-center text-gray-500 dark:text-gray-400 mt-10">
            <Bot className="w-12 h-12 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
            <p>{t('promptStart')}</p>
            <button
              onClick={onStartSession}
              aria-label="Start Session"
              className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              disabled={isStartingSession}
            >
              {isStartingSession ? t('startingSession') : t('startSession')}
            </button>
          </div>
        )}

        <LearningMessageList
          messages={messages}
          editingMessageIndex={editingMessageIndex}
          onEditMessage={onEditMessage}
          onUpdateSymbols={onUpdateSymbols}
          onCancelEdit={onCancelEdit}
        />

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 dark:bg-gray-700 rounded-2xl rounded-bl-none px-4 py-3">
              <div className="flex space-x-2">
                <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce delay-75" />
                <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce delay-150" />
              </div>
            </div>
          </div>
        )}
      </div>

      <LearningInputRow
        input={input}
        onInputChange={onInputChange}
        onSubmit={onSubmit}
        voiceEnabled={voiceEnabled}
        isRecording={isRecording}
        hasRecording={hasRecording}
        isLoading={isLoading}
        isStartingSession={isStartingSession}
        boardId={currentSession?.board_id ?? null}
        startRecording={startRecording}
        stopRecording={stopRecording}
        sendRecording={sendRecording}
        discardRecording={discardRecording}
      />
    </div>
  );
}
