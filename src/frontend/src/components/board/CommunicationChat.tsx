import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Bot, Send, Mic, Square, Volume2, Trash2 } from 'lucide-react';
import { useLearningStore, stripReasoning } from '../../store/learningStore';
import { useAuthStore } from '../../store/authStore';
import { useTranslation } from 'react-i18next';
import { tts } from '../../lib/tts';
import { useVoiceRecorder } from '../learning/useVoiceRecorder';
import { useToastStore } from '../../store/toastStore';
import { Button } from '../ui/button';
import { cn } from '@/lib/utils';

interface CommunicationChatProps {
  voiceEnabled: boolean;
  onVoiceToggle: () => void;
  boardId: number;
  boardName: string;
}

export function CommunicationChat({ voiceEnabled, onVoiceToggle, boardId, boardName }: CommunicationChatProps) {
  const { t, i18n } = useTranslation('learning');
  const user = useAuthStore((state) => state.user);
  const messages = useLearningStore((state) => state.messages);
  const isLoading = useLearningStore((state) => state.isLoading);
  const currentSession = useLearningStore((state) => state.currentSession);
  const startSession = useLearningStore((state) => state.startSession);
  const submitAnswer = useLearningStore((state) => state.submitAnswer);
  const submitVoiceAnswer = useLearningStore((state) => state.submitVoiceAnswer);
  const showAdminReasoning = useLearningStore((state) => state.showAdminReasoning);
  const error = useLearningStore((state) => state.error);

  const [input, setInput] = useState('');
  const addToast = useToastStore((state) => state.addToast);
  const lastSpokenMessageRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const initAttempted = useRef(false);
  const topic = boardName.trim() || t('topics.general');

  const resolveAssistantText = useCallback((raw: string) => {
    if (!raw) return raw;
    if (i18n.exists(raw, { ns: 'learning' })) {
      return t(raw, {
        name: user?.display_name || user?.username || '',
        topic,
      });
    }
    return raw;
  }, [i18n, t, topic, user?.display_name, user?.username]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-start session if none exists. A failed attempt resets the guard so a
  // later state change (e.g. the user opening the chat again) retries instead
  // of leaving the chat permanently without a session.
  useEffect(() => {
    if (!currentSession && user && !isLoading && !error && !initAttempted.current) {
      initAttempted.current = true;
      startSession({
        topic,
        purpose: 'communication board',
        difficulty: 'adaptive',
        board_id: boardId,
      }, user.id).catch(err => {
        console.error('Failed to auto-start session:', err);
        initAttempted.current = false;
      });
    }
  }, [currentSession, user, startSession, isLoading, error, topic, boardId]);

  // Auto-speak assistant messages
  useEffect(() => {
    if (!voiceEnabled || messages.length === 0) return;

    const lastMsg = messages[messages.length - 1];
    if (lastMsg.role === 'assistant') {
      const content = resolveAssistantText(lastMsg.content);

      if (content === lastSpokenMessageRef.current) return;
      lastSpokenMessageRef.current = content;

      const textToSpeak = showAdminReasoning ? content : stripReasoning(content);
      if (textToSpeak) {
        tts.enqueue(textToSpeak, { rate: 0.9 });
      }
    }
  }, [messages, resolveAssistantText, showAdminReasoning, voiceEnabled]);

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim()) return;

    // Sending with no active session (e.g. the auto-start failed) must not
    // fail silently: start one on demand, then submit the message.
    let activeSession = currentSession;
    if (!activeSession && user) {
      try {
        await startSession({
          topic,
          purpose: 'communication board',
          difficulty: 'adaptive',
          board_id: boardId,
        }, user.id);
        activeSession = useLearningStore.getState().currentSession;
      } catch (err) {
        console.error('Failed to start session for chat message:', err);
        addToast(t('common:sessionStartFailed'), 'error');
        return;
      }
    }
    if (!activeSession) return;

    const answer = input;
    setInput('');
    await submitAnswer(activeSession.session_id, answer);
  };

  const {
    isRecording,
    hasRecording,
    startRecording,
    stopRecording,
    discardRecording,
    sendRecording,
  } = useVoiceRecorder({
    currentSession,
    userId: user?.id,
    isLoading,
    sessionDifficulty: 'adaptive',
    startSession,
    submitVoiceAnswer,
    addToast,
    microphoneAccessMessage: t('errors.microphoneAccess'),
    sessionTopic: topic,
    sessionBoardId: boardId,
  });

  return (
    <div className="flex flex-col h-full glass-panel border-l border-border">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between bg-background/50">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-brand/10 text-brand">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="font-semibold text-foreground text-sm">{t('aiAssistant')}</div>
            <div className="text-xs text-muted-foreground">
              {t('conversationPartner')}
            </div>
          </div>
        </div>
        <button
          onClick={onVoiceToggle}
          className={cn(
            'rounded-lg p-2 transition-colors',
            voiceEnabled ? 'bg-brand/10 text-brand' : 'bg-muted text-muted-foreground',
          )}
          title={voiceEnabled ? t('voiceOn') : t('voiceOff')}
        >
          <Volume2 className={cn('w-4 h-4', !voiceEnabled && 'opacity-50')} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300" role="alert">
            {t('errorPrefix', { message: error })}
          </div>
        )}
        {messages.length === 0 && (
          <div className="text-center text-muted-foreground mt-10 text-sm">
            <p>{t('startChatting')}</p>
          </div>
        )}

        {messages.map((message, index) => (
          // Resolve backend translation keys through the active locale.
          // resolve it for display using the learning namespace.
          <div
            key={index}
            className={cn('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}
          >
            <div
              className={cn(
            'max-w-[85%] rounded-2xl px-4 py-2 text-sm',
            message.role === 'user'
              ? 'rounded-br-none bg-brand text-white'
              : 'rounded-bl-none bg-muted text-foreground',
          )}
            >
              <p className="whitespace-pre-wrap">
                {message.role === 'assistant' ? resolveAssistantText(message.content) : message.content}
              </p>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-2xl rounded-bl-none px-4 py-3">
              <div className="flex space-x-2">
                <div className="w-1.5 h-1.5 bg-muted-foreground rounded-full animate-bounce" />
                <div className="w-1.5 h-1.5 bg-muted-foreground rounded-full animate-bounce delay-75" />
                <div className="w-1.5 h-1.5 bg-muted-foreground rounded-full animate-bounce delay-150" />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-3 border-t border-border bg-background">
        <form onSubmit={handleSend} className="flex gap-2">
          <input
            id="communication-chat-input"
            name="communication_chat_input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('typeAnswer')}
            className="flex-1 p-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand bg-surface text-foreground"
            disabled={isLoading || isRecording}
          />

          {isRecording ? (
            <button
              type="button"
              onClick={stopRecording}
              className="p-2 bg-red-500 text-white rounded-lg animate-pulse"
            >
              <Square className="w-5 h-5" />
            </button>
          ) : hasRecording ? (
            <>
              <Button
                type="button"
                variant="success"
                size="icon"
                onClick={sendRecording}
                disabled={isLoading}
              >
                <Send />
              </Button>
              <button
                type="button"
                onClick={discardRecording}
                className="p-2 bg-muted text-muted-foreground rounded-lg"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={startRecording}
              className="p-2 bg-muted text-muted-foreground rounded-lg hover:bg-surface-hover"
              disabled={isLoading}
            >
              <Mic className="w-5 h-5" />
            </button>
          )}

          <Button type="submit" disabled={isLoading || (!input.trim() && !isRecording)} className="p-2" >
            <Send className="w-5 h-5" />
          </Button>
        </form>
      </div>
    </div>
  );
}
