import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Bot, LogOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LearningInputRow } from './LearningInputRow';
import { LearningMessageList, type LearningMessage } from './LearningMessageList';
import { LearningQuestionCard } from './LearningQuestionCard';
import type { LearningSessionResponse, QuestionResponse } from '../../types';
import type { LearningProgress, RevealedAnswer } from '../../store/learningStore';
import { Button } from '../ui/button';

interface LearningChatPanelProps {
  messages: LearningMessage[];
  isLoading: boolean;
  error: string | null;
  isStartingSession: boolean;
  sessionStartError: string | null;
  currentSession: LearningSessionResponse | null;
  currentQuestion: QuestionResponse | null;
  revealed: RevealedAnswer | null;
  progress: LearningProgress | null;
  onAnswerQuestion: (choice: string) => void;
  onEndSession: () => void;
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
  currentQuestion,
  revealed,
  progress,
  onAnswerQuestion,
  onEndSession,
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
  const [showEndConfirmation, setShowEndConfirmation] = useState(false);
  const conversationRef = useRef<HTMLDivElement | null>(null);
  const endSessionRef = useRef<HTMLDivElement | null>(null);
  const endSessionButtonRef = useRef<HTMLButtonElement | null>(null);
  const cancelEndRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const conversation = conversationRef.current;
    if (!conversation) return;
    if (typeof conversation.scrollTo === 'function') {
      conversation.scrollTo({ top: conversation.scrollHeight, behavior: 'smooth' });
    } else {
      conversation.scrollTop = conversation.scrollHeight;
    }
  }, [messages.length, isLoading, error, sessionStartError]);

  useEffect(() => {
    if (!showEndConfirmation) return;

    const triggerButton = endSessionButtonRef.current;
    cancelEndRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setShowEndConfirmation(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      // Cancel/Escape removes the focused Cancel button. Return focus to the
      // trigger when it still exists; after confirmation the session may close
      // and remove the trigger immediately afterward.
      if (triggerButton && document.contains(triggerButton)) {
        triggerButton.focus();
      }
    };
  }, [showEndConfirmation]);

  const handleEndSessionClick = () => {
    if (isLoading) return;
    setShowEndConfirmation(true);
  };

  const confirmEndSession = () => {
    setShowEndConfirmation(false);
    onEndSession();
  };

  const difficultyLabels: Record<string, string> = {
    basic: t('difficulty.basic'),
    intermediate: t('difficulty.intermediate'),
    advanced: t('difficulty.advanced'),
  };
  const progressPercent =
    progress?.comprehensionScore !== undefined
      ? Math.round(progress.comprehensionScore * 100)
      : undefined;

  return (
    <div className="flex-1 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex flex-wrap items-start gap-3 bg-gray-50 dark:bg-gray-900/50">
        <div className="min-w-0 flex flex-1 items-start gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300">
            <Bot className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-gray-900 dark:text-gray-100 text-sm break-words">
              {t('title')}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {t('panelSubtitle')}
            </div>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {currentSession && progress && (progressPercent !== undefined || progress.difficulty) && (
            <div className="flex items-center gap-2" data-testid="progress-chips">
              {progressPercent !== undefined && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                  {t('score')} {progressPercent}%
                </span>
              )}
              {progress.questionsAnswered !== undefined && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800">
                  {t('correctAnswers')} {progress.correctAnswers ?? 0}/{progress.questionsAnswered}
                </span>
              )}
              {progress.difficulty && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
                  {t('level')}: {difficultyLabels[progress.difficulty] ?? progress.difficulty}
                </span>
              )}
            </div>
          )}
          {isAdmin && (
            <label className="flex max-w-full items-center gap-1 cursor-pointer select-none text-xs text-gray-500 dark:text-gray-400">
              <input
                id="show-admin-reasoning"
                name="show_admin_reasoning"
                type="checkbox"
                className="mr-1"
                checked={showAdminReasoning}
                onChange={(event) => onShowAdminReasoningChange(event.target.checked)}
              />
              <span>{t('showThinking')}</span>
            </label>
          )}
          {currentSession && (
            <div ref={endSessionRef} className="relative">
              <button
                ref={endSessionButtonRef}
                type="button"
                onClick={handleEndSessionClick}
                disabled={isLoading}
                aria-expanded={showEndConfirmation}
                aria-haspopup="dialog"
                aria-controls="end-session-confirmation"
                data-testid="learning-session-active"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={t('endSessionTitle')}
              >
                <LogOut className="w-3.5 h-3.5" />
                {t('endSession')}
              </button>
              {showEndConfirmation && (
                <div
                  id="end-session-confirmation"
                  role="dialog"
                  aria-modal="false"
                  aria-labelledby="end-session-confirmation-title"
                  aria-describedby="end-session-confirmation-description"
                  className="absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-red-200 dark:border-red-800 bg-white dark:bg-gray-800 p-4 shadow-xl"
                >
                  <p
                    id="end-session-confirmation-title"
                    className="text-sm font-semibold text-gray-900 dark:text-gray-100"
                  >
                    {t('endSessionConfirmTitle')}
                  </p>
                  <p
                    id="end-session-confirmation-description"
                    className="mt-1 text-xs leading-relaxed text-gray-600 dark:text-gray-300"
                  >
                    {t('endSessionConfirm')}
                  </p>
                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      ref={cancelEndRef}
                      type="button"
                      onClick={() => setShowEndConfirmation(false)}
                      className="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                    >
                      {t('cancel')}
                    </button>
                    <Button
                      type="button"
                      variant="danger"
                      size="xs"
                      onClick={confirmEndSession}
                    >
                      {t('endSession')}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div
        ref={conversationRef}
        className="flex-1 overflow-y-auto p-4 space-y-4"
        role="log"
        aria-label={t('conversationHistory')}
        tabIndex={0}
      >
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
            <p className="font-medium">{t('errorPrefix', { message: error })}</p>
          </div>
        )}

        {messages.length === 0 && !isLoading && !currentSession && !isStartingSession && (
          <div className="text-center text-gray-500 dark:text-gray-400 mt-10">
            <Bot className="w-12 h-12 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
            <p>{t('promptStart')}</p>
            <Button onClick={onStartSession} aria-label={t('startSessionLabel')} data-testid="learning-session-start" className="mt-4" disabled={isStartingSession} >
              {isStartingSession ? t('startingSession') : t('startSession')}
            </Button>
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

      <LearningQuestionCard
        question={currentQuestion}
        disabled={isLoading}
        onAnswer={onAnswerQuestion}
        revealed={revealed}
      />

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
