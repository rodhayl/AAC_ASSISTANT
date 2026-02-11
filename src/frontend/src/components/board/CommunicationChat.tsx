import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Bot, Send, Mic, Square, Volume2, Trash2 } from 'lucide-react';
import { useLearningStore, stripReasoning } from '../../store/learningStore';
import { useAuthStore } from '../../store/authStore';
import { useTranslation } from 'react-i18next';
import { tts } from '../../lib/tts';

interface CommunicationChatProps {
  voiceEnabled: boolean;
  onVoiceToggle: () => void;
}

export function CommunicationChat({ voiceEnabled, onVoiceToggle }: CommunicationChatProps) {
  const { t, i18n } = useTranslation('learning');
  const { user } = useAuthStore();
  const {
    messages,
    isLoading,
    currentSession,
    startSession,
    submitAnswer,
    submitVoiceAnswer,
    showAdminReasoning,
    error
  } = useLearningStore();

  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [hasRecording, setHasRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const lastSpokenMessageRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const initAttempted = useRef(false);

  const resolveAssistantText = useCallback((raw: string) => {
    if (!raw) return raw;
    if (i18n.exists(raw, { ns: 'learning' })) {
      return t(raw, {
        name: user?.display_name || user?.username || '',
        topic: currentSession?.topic || 'general'
      });
    }
    return raw;
  }, [currentSession?.topic, i18n, t, user?.display_name, user?.username]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-start session if none exists
  useEffect(() => {
    if (!currentSession && user && !isLoading && !error && !initAttempted.current) {
      initAttempted.current = true;
      startSession({
        topic: 'general conversation',
        purpose: 'communication board',
        difficulty: 'adaptive'
      }, user.id).catch(err => {
        console.error('Failed to auto-start session:', err);
      });
    }
  }, [currentSession, user, startSession, isLoading, error]);

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
    if (!input.trim() || !currentSession) return;

    const answer = input;
    setInput('');
    await submitAnswer(currentSession.session_id, answer);
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = () => {
        setHasRecording(true);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Error accessing microphone:', err);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const discardRecording = () => {
    chunksRef.current = [];
    setHasRecording(false);
  };

  const sendRecording = async () => {
    if (!currentSession || chunksRef.current.length === 0 || isLoading) return;
    const audioBlob = new Blob(chunksRef.current, { type: 'audio/wav' });
    await submitVoiceAnswer(currentSession.session_id, audioBlob);
    chunksRef.current = [];
    setHasRecording(false);
  };

  return (
    <div className="flex flex-col h-full glass-panel border-l border-border dark:border-white/5">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-gray-900/50">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="font-semibold text-gray-900 dark:text-gray-100 text-sm">AI Assistant</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Conversation Partner
            </div>
          </div>
        </div>
        <button
          onClick={onVoiceToggle}
          className={`p-2 rounded-lg transition-colors ${voiceEnabled
              ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
            }`}
          title={voiceEnabled ? 'Voice Output On' : 'Voice Output Off'}
        >
          <Volume2 className={`w-4 h-4 ${!voiceEnabled && 'opacity-50'}`} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 mt-10 text-sm">
            <p>{t('startChatting', 'Start chatting using the board or type here.')}</p>
          </div>
        )}

        {messages.map((message, index) => (
          // If the backend returns a translation key (e.g. fallbackConversation.goodMessage),
          // resolve it for display using the learning namespace.
          <div
            key={index}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${message.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-br-none'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-bl-none'
                }`}
            >
              <p className="whitespace-pre-wrap">
                {message.role === 'assistant' ? resolveAssistantText(message.content) : message.content}
              </p>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 dark:bg-gray-700 rounded-2xl rounded-bl-none px-4 py-3">
              <div className="flex space-x-2">
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce delay-75" />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce delay-150" />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
        <form onSubmit={handleSend} className="flex gap-2">
          <input
            id="communication-chat-input"
            name="communication_chat_input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('typeAnswer')}
            className="flex-1 p-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
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
              <button
                type="button"
                onClick={sendRecording}
                className="p-2 bg-green-600 text-white rounded-lg"
                disabled={isLoading}
              >
                <Send className="w-5 h-5" />
              </button>
              <button
                type="button"
                onClick={discardRecording}
                className="p-2 bg-gray-200 dark:bg-gray-700 text-gray-600 rounded-lg"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={startRecording}
              className="p-2 bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-300"
              disabled={isLoading}
            >
              <Mic className="w-5 h-5" />
            </button>
          )}

          <button
            type="submit"
            disabled={isLoading || (!input.trim() && !isRecording)}
            className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
}
