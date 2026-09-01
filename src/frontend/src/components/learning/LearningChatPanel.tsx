import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Bot, LogOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LearningInputRow } from './LearningInputRow';
import { LearningMessageList, type LearningMessage } from './LearningMessageList';
import { LearningQuestionCard } from './LearningQuestionCard';
import type { LearningSessionResponse, QuestionResponse } from '../../types';
import type { LearningProgress, RevealedAnswer } from '../../store/learningStore';
import { Button } from '../ui/button';
import { StatusMessage } from '../ui/StatusMessage';

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
    <div className="flex-1 bg-surface rounded-xl shadow-sm border border-border flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex flex-wrap items-start gap-3 bg-background/50">
        <div className="min-w-0 flex flex-1 items-start gap-2">
          <div className="p-1.5 rounded-lg bg-brand/10 text-brand">
            <Bot className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-foreground text-sm break-words">
              {t('title')}
            </div>
            <div className="text-xs text-muted-foreground">
              {t('panelSubtitle')}
            </div>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {currentSession && progress && (progressPercent !== undefined || progress.difficulty) && (
            <div className="flex items-center gap-2" data-testid="progress-chips">
              {progressPercent !== undefined && (
                <StatusMessage variant="success" className="inline-flex items-center gap-1 rounded-full border-emerald-200 px-2.5 py-1 text-xs font-medium dark:border-emerald-800">

                  {t('score')} {progressPercent}%
                </StatusMessage>
              )}
              {progress.questionsAnswered !== undefined && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-brand/10 text-brand border border-brand/20">
                  {t('correctAnswers')} {progress.correctAnswers ?? 0}/{progress.questionsAnswered}
                </span>
              )}
              {progress.difficulty && (
                <StatusMessage variant="warning" className="inline-flex items-center gap-1 rounded-full border-amber-200 px-2.5 py-1 text-xs font-medium dark:border-amber-800">

                  {t('level')}: {difficultyLabels[progress.difficulty] ?? progress.difficulty}
                </StatusMessage>
              )}
            </div>
          )}
          {isAdmin && (
            <label className="flex max-w-full items-center gap-1 cursor-pointer select-none text-xs text-muted-foreground">
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
                  className="absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-red-200 dark:border-red-800 bg-surface p-4 shadow-xl"
                >
                  <p
                    id="end-session-confirmation-title"
                    className="text-sm font-semibold text-foreground"
                  >
                    {t('endSessionConfirmTitle')}
                  </p>
                  <p
                    id="end-session-confirmation-description"
                    className="mt-1 text-xs leading-relaxed text-muted-foreground"
                  >
                    {t('endSessionConfirm')}
                  </p>
                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      ref={cancelEndRef}
                      type="button"
                      onClick={() => setShowEndConfirmation(false)}
                      className="rounded-lg px-3 py-1.5 text-xs font-medium text-foreground hover:bg-surface-hover"
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
          <div className="flex justify-center items-center p-6 bg-brand/10 rounded-lg border border-brand/20">
            <div className="text-center">
              <div className="inline-flex items-center justify-center mb-3">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
              </div>
              <p className="text-brand font-medium">
                {t('startingSession')}
              </p>
              <p className="text-brand text-sm mt-1">{t('mayTake')}</p>
            </div>
          </div>
        )}

        {sessionStartError && (
          <StatusMessage variant="error">
            <p className="font-medium">{sessionStartError}</p>
          </StatusMessage>
        )}

        {error && (
          <StatusMessage variant="error">
            <p className="font-medium">{t('errorPrefix', { message: error })}</p>
          </StatusMessage>
        )}

        {messages.length === 0 && !isLoading && !currentSession && !isStartingSession && (
          <div className="text-center text-muted-foreground mt-10">
            <Bot className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
            <p>{t('promptStart')}</p>
            <Button onClick={onStartSession} aria-label={t('startSessionLabel')} data-testid="learning-session-start" className="mt-4" disabled={isStartingSession} >
              {isStartingSession ? t('startingSession') : t('startSession')}
            </Button>
          </div>
        )}

        <LearningMessageList
          messages={messages}
          editingMessageIndex={editingMessageIndex}
          sessionId={currentSession?.session_id}
          onEditMessage={onEditMessage}
          onUpdateSymbols={onUpdateSymbols}
          onCancelEdit={onCancelEdit}
        />

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-2xl rounded-bl-none px-4 py-3">
              <div className="flex space-x-2">
                <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce delay-75" />
                <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce delay-150" />
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
        topic={currentSession?.topic ?? null}
        startRecording={startRecording}
        stopRecording={stopRecording}
        sendRecording={sendRecording}
        discardRecording={discardRecording}
      />
    </div>
  );
}
