import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useLearningStore, stripReasoning } from '../store/learningStore';
import { useAuthStore } from '../store/authStore';
import { useBoardStore } from '../store/boardStore';
import { loadTopicsForUser, saveTopicsForUser, type SavedTopic } from '../lib/learningTopics';
import api from '../lib/api';
import { glossSymbolUtterance } from '../lib/gloss';
import { tts } from '../lib/tts';
import { useToastStore } from '../store/toastStore';
import { BoardsAndTopicsSidebar } from '../components/learning/BoardsAndTopicsSidebar';
import { LearningChatPanel } from '../components/learning/LearningChatPanel';
import { LearningHistoryPanel } from '../components/learning/LearningHistoryPanel';
import { LearningHeader } from '../components/learning/LearningHeader';
import { LearningSymbolPanel } from '../components/learning/LearningSymbolPanel';
import type { LearningSymbolItem } from '../types';
import { SessionSummaryModal } from '../components/learning/SessionSummaryModal';
import { useVoiceRecorder } from '../components/learning/useVoiceRecorder';
import { dedupeLearningSymbols } from '../lib/symbols';

type SymbolItem = LearningSymbolItem;

export function Learning() {
  const messages = useLearningStore((state) => state.messages);
  const isLoading = useLearningStore((state) => state.isLoading);
  const error = useLearningStore((state) => state.error);
  const clearError = useLearningStore((state) => state.clearError);
  const currentSession = useLearningStore((state) => state.currentSession);
  const currentQuestion = useLearningStore((state) => state.currentQuestion);
  const revealedAnswer = useLearningStore((state) => state.revealedAnswer);
  const progressStats = useLearningStore((state) => state.progressStats);
  const lastSessionSummary = useLearningStore((state) => state.lastSessionSummary);
  const clearSessionSummary = useLearningStore((state) => state.clearSessionSummary);
  const endSession = useLearningStore((state) => state.endSession);
  const sessionHistory = useLearningStore((state) => state.sessionHistory);
  const isLoadingHistory = useLearningStore((state) => state.isLoadingHistory);
  const startSession = useLearningStore((state) => state.startSession);
  const askQuestion = useLearningStore((state) => state.askQuestion);
  const askNextQuestion = useLearningStore((state) => state.askNextQuestion);
  const submitAnswer = useLearningStore((state) => state.submitAnswer);
  const submitVoiceAnswer = useLearningStore((state) => state.submitVoiceAnswer);
  const submitSymbolAnswer = useLearningStore((state) => state.submitSymbolAnswer);
  const fetchSessionHistory = useLearningStore((state) => state.fetchSessionHistory);
  const loadSession = useLearningStore((state) => state.loadSession);
  const showAdminReasoning = useLearningStore((state) => state.showAdminReasoning);
  const setShowAdminReasoning = useLearningStore((state) => state.setShowAdminReasoning);
  const providerInUse = useLearningStore((state) => state.providerInUse);
  const providerHistory = useLearningStore((state) => state.providerHistory);
  const setAutoAskEnabled = useLearningStore((state) => state.setAutoAskEnabled);
  const difficultyOverride = useLearningStore((state) => state.difficultyOverride);
  const setDifficultyOverride = useLearningStore((state) => state.setDifficultyOverride);
  const user = useAuthStore((state) => state.user);
  const addToast = useToastStore((state) => state.addToast);
  const fetchBoards = useBoardStore((state) => state.fetchBoards);
  const { t, i18n } = useTranslation('learning');
  const currentLang = i18n.language?.split('-')[0] || 'en';

  const [input, setInput] = useState('');
  const [voiceEnabled, setVoiceEnabled] = useState(user?.settings?.voice_mode_enabled ?? true);
  const [showHistory, setShowHistory] = useState(false);
  const [selectedModeKey, setSelectedModeKey] = useState('practice');
  const [availableModes, setAvailableModes] = useState<Array<{ id: number; name: string; key: string; description: string; auto_ask_enabled?: boolean }>>([]);
  const [savedTopics, setSavedTopics] = useState<SavedTopic[]>([]);
  const [symbolView, setSymbolView] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState('');
  const [symbolItems, setSymbolItems] = useState<SymbolItem[]>([]);
  const [symbolLoading, setSymbolLoading] = useState(false);
  const [symbolUtterance, setSymbolUtterance] = useState<SymbolItem[]>([]);
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [isBoardsOpen, setIsBoardsOpen] = useState(true);
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [sessionStartError, setSessionStartError] = useState<string | null>(null);
  const [providerNotice, setProviderNotice] = useState<string | null>(null);
  const lastSpokenMessageRef = useRef<string | null>(null);
  const lastProviderHistoryLengthRef = useRef(0);

  const isAdmin = user?.user_type === 'admin';
  // Session metadata still needs a concrete starting level. "Adaptive" starts
  // at basic and lets the backend adjust; a fixed override is sent verbatim.
  const sessionDifficulty = difficultyOverride === 'adaptive' ? 'basic' : difficultyOverride;

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
    startSession,
    submitVoiceAnswer,
    addToast,
    microphoneAccessMessage: t('errors.microphoneAccess'),
    sessionDifficulty,
  });

  useEffect(() => {
    if (user?.settings?.voice_mode_enabled !== undefined) {
      setVoiceEnabled(user.settings.voice_mode_enabled);
    }
  }, [user?.settings?.voice_mode_enabled]);

  useEffect(() => {
    if (!user?.id) return;
    setSavedTopics(loadTopicsForUser(user.id));
  }, [user?.id]);

  useEffect(() => {
    if (!user?.id) return;
    saveTopicsForUser(user.id, savedTopics);
  }, [savedTopics, user?.id]);

  useEffect(() => {
    if (!user?.id) return;
    fetchBoards(user.id);
    api.get('/learning-modes/')
      .then((response) => setAvailableModes(response.data))
      .catch((fetchError) => console.error('Failed to fetch learning modes', fetchError));
  }, [fetchBoards, user?.id]);

  useEffect(() => {
    if (user?.id) {
      fetchSessionHistory(user.id);
    }
  }, [fetchSessionHistory, user?.id]);

  // The selected mode may disable auto-asking (e.g. conversational modes like
  // roleplay). Combined with symbol-first view, auto-asking is paused: the
  // question card is hidden and auto-asks are skipped, while the manual
  // "New question" button still works.
  const selectedModeAutoAsk = useMemo(() => {
    const mode = availableModes.find((item) => item.key === selectedModeKey);
    return mode?.auto_ask_enabled !== false;
  }, [availableModes, selectedModeKey]);

  useEffect(() => {
    setAutoAskEnabled(!symbolView && selectedModeAutoAsk);
  }, [selectedModeAutoAsk, setAutoAskEnabled, symbolView]);

  const startActivity = useCallback(async (topic: string, purpose: string, boardId?: number) => {
    if (!user) return;
    setIsStartingSession(true);
    setSessionStartError(null);
    try {
      await startSession({ topic, purpose, difficulty: sessionDifficulty, board_id: boardId, mode_key: selectedModeKey }, user.id);
      await fetchSessionHistory(user.id);
      // Auto-request the first adaptive question now that the session is active
      void askNextQuestion();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('errors.unknownError');
      setSessionStartError(t('errors.sessionStartError', { error: message }));
      setTimeout(() => setSessionStartError(null), 8000);
    } finally {
      setIsStartingSession(false);
    }
  }, [askNextQuestion, fetchSessionHistory, selectedModeKey, sessionDifficulty, startSession, t, user]);

  const handleToggleHistory = useCallback(() => {
    const nextVisible = !showHistory;
    setShowHistory(nextVisible);
    if (nextVisible && user?.id) {
      void fetchSessionHistory(user.id);
    }
  }, [fetchSessionHistory, showHistory, user?.id]);

  const handleNewConversation = useCallback(async () => {
    await startActivity('general conversation', 'practice');
    setShowHistory(false);
  }, [startActivity]);
  // Submit an answer; the store auto-requests the next adaptive question.
  const answerAndContinue = useCallback(async (answer: string) => {
    if (!currentSession) return;
    await submitAnswer(currentSession.session_id, answer);
  }, [currentSession, submitAnswer]);

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!input.trim()) return;
    clearError();

    if (!currentSession) {
      setSessionStartError(t('errors.startSessionFirst'));
      setTimeout(() => setSessionStartError(null), 5000);
      return;
    }
    const answer = input;
    setInput('');
    await answerAndContinue(answer);
  };

  // Manual request bypasses the auto-ask gate so teachers can still pull a
  // question in modes where auto-asking is disabled.
  const handleNewQuestion = useCallback(() => {
    if (isLoading || !currentSession) return;
    const requestedDifficulty = difficultyOverride === 'adaptive' ? undefined : difficultyOverride;
    void askQuestion(currentSession.session_id, requestedDifficulty);
  }, [askQuestion, currentSession, difficultyOverride, isLoading]);

  const handleEndSession = useCallback(async () => {
    if (!currentSession || isLoading) return;
    await endSession(currentSession.session_id);
  }, [currentSession, endSession, isLoading]);

  const handleLoadSession = async (sessionId: number) => {
    await loadSession(sessionId);
    setShowHistory(false);
  };

  const sendSymbolUtterance = async () => {
    if (symbolUtterance.length === 0 || isLoading || !user) return;
    let sessionId = currentSession?.session_id;

    if (!sessionId) {
      setIsStartingSession(true);
      setSessionStartError(null);
      try {
        await startSession({
          topic: 'symbol conversation',
          purpose: 'aac symbols',
          difficulty: sessionDifficulty,
          mode_key: selectedModeKey,
        }, user.id);
        sessionId = useLearningStore.getState().currentSession?.session_id;
        if (!sessionId) {
          setSessionStartError(t('errors.sessionStartFailed'));
          setIsStartingSession(false);
          return;
        }
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : t('errors.unknownError');
        setSessionStartError(t('errors.sessionStartError', { error: message }));
        setTimeout(() => setSessionStartError(null), 8000);
        setIsStartingSession(false);
        return;
      }
    }

    if (!sessionId) {
      setIsStartingSession(false);
      return;
    }

    try {
      const enrichedGloss = glossSymbolUtterance(symbolUtterance);
      const rawGloss = symbolUtterance.map((symbol) => symbol.label).join(' ');
      await submitSymbolAnswer(sessionId, symbolUtterance, enrichedGloss, rawGloss);
      setSymbolUtterance([]);
    } finally {
      setIsStartingSession(false);
    }
  };

  const fetchSymbols = useCallback(async () => {
    setSymbolLoading(true);
    try {
      const response = await api.get('/boards/symbols', {
        params: { limit: 1000, language: currentLang },
      });
      setSymbolItems(dedupeLearningSymbols(response.data || []));
    } catch {
      setSymbolItems([]);
    } finally {
      setSymbolLoading(false);
    }
  }, [currentLang]);

  useEffect(() => {
    if (!symbolView) return;
    fetchSymbols();
    setIsBoardsOpen(false);
  }, [fetchSymbols, symbolView]);

  const filteredSymbols = useMemo(() => {
    let items = symbolItems;
    if (symbolSearch) {
      const query = symbolSearch.toLowerCase();
      items = items.filter((symbol) =>
        symbol.label.toLowerCase().includes(query) ||
        (symbol.keywords && symbol.keywords.toLowerCase().includes(query)),
      );
    }

    if (selectedCategory !== 'all') {
      items = selectedCategory === 'food'
        ? items.filter((symbol) => symbol.category === 'food' || symbol.category === 'drinks')
        : items.filter((symbol) => symbol.category === selectedCategory);
    }
    return items;
  }, [selectedCategory, symbolItems, symbolSearch]);

  const coreWords = useMemo(() => {
    const coreWordsByLanguage: Record<string, string[]> = {
      en: ['I', 'you', 'want', 'go', 'stop', 'help', 'yes', 'no', 'more', 'finished', 'like', 'eat', 'drink'],
      es: ['yo', 'tú', 'quiero', 'ir', 'parar', 'ayuda', 'sí', 'no', 'más', 'terminado', 'me gusta', 'comer', 'beber'],
    };
    const priorityWords = coreWordsByLanguage[currentLang] || coreWordsByLanguage.en;
    const byLabel = new Map<string, SymbolItem>();

    symbolItems
      .filter((symbol) => priorityWords.includes(symbol.label))
      .forEach((symbol) => {
        const key = symbol.label.trim().toLowerCase();
        const existing = byLabel.get(key);
        if (!existing || (!existing.image_path && symbol.image_path)) {
          byLabel.set(key, symbol);
        }
      });

    return Array.from(byLabel.values()).sort((a, b) =>
      priorityWords.indexOf(a.label) - priorityWords.indexOf(b.label),
    );
  }, [currentLang, symbolItems]);

  useEffect(() => {
    const currentLength = providerHistory.length;
    if (currentLength <= lastProviderHistoryLengthRef.current || currentLength === 0) return;

    const last = providerHistory[currentLength - 1];
    lastProviderHistoryLengthRef.current = currentLength;
    const providerName =
      last.provider === 'openrouter'
        ? 'OpenRouter'
        : last.provider === 'lmstudio'
          ? 'LM Studio'
          : 'Ollama';
    Promise.resolve().then(() => {
      setProviderNotice(`Switched to ${providerName}`);
    });
    const timeoutId = setTimeout(() => setProviderNotice(null), 3000);
    return () => clearTimeout(timeoutId);
  }, [providerHistory]);

  useEffect(() => {
    if (!voiceEnabled || messages.length === 0) return;
    const lastMessage = messages[messages.length - 1];
    if (lastMessage.role !== 'assistant' || lastMessage.content === lastSpokenMessageRef.current) return;

    lastSpokenMessageRef.current = lastMessage.content;
    const textToSpeak = stripReasoning(lastMessage.content);
    if (textToSpeak) {
      tts.enqueue(textToSpeak, { rate: 0.9 });
    }
  }, [messages, voiceEnabled]);

  const updateSymbolMessage = async (symbols: Array<{
    id: number;
    label: string;
    image_path?: string;
    category?: string;
  }>) => {
    if (!currentSession || symbols.length === 0) return;
    const enrichedGloss = glossSymbolUtterance(symbols);
    const rawGloss = symbols.map((symbol) => symbol.label).join(' ');
    await submitSymbolAnswer(currentSession.session_id, symbols, enrichedGloss, rawGloss);
  };

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col">
      <LearningHeader
        showHistory={showHistory}
        onToggleHistory={handleToggleHistory}
        symbolView={symbolView}
        onToggleSymbolView={() => setSymbolView((visible) => !visible)}
        selectedModeKey={selectedModeKey}
        onModeChange={setSelectedModeKey}
        availableModes={availableModes}
        difficultyOverride={difficultyOverride}
        onDifficultyChange={setDifficultyOverride}
        providerInUse={providerInUse}
        providerNotice={providerNotice}
        voiceEnabled={voiceEnabled}
        onToggleVoice={() => setVoiceEnabled((enabled) => !enabled)}
        onNewQuestion={handleNewQuestion}
        canAskQuestion={Boolean(currentSession) && !isLoading && !symbolView}
      />

      <div className="flex-1 flex gap-4 overflow-hidden">
        {showHistory && (
          <LearningHistoryPanel
            sessionHistory={sessionHistory}
            isLoadingHistory={isLoadingHistory}
            currentSessionId={currentSession?.session_id}
            onLoadSession={handleLoadSession}
            onNewConversation={handleNewConversation}
          />
        )}

        <LearningChatPanel
          messages={messages}
          isLoading={isLoading}
          error={error}
          isStartingSession={isStartingSession}
          sessionStartError={sessionStartError}
          currentSession={currentSession}
          currentQuestion={symbolView ? null : currentQuestion}
          revealed={revealedAnswer}
          progress={progressStats}
          onAnswerQuestion={(choice) => { void answerAndContinue(choice); }}
          onEndSession={() => { void handleEndSession(); }}
          isAdmin={isAdmin}
          showAdminReasoning={showAdminReasoning}
          onShowAdminReasoningChange={setShowAdminReasoning}
          onStartSession={() => { void handleNewConversation(); }}
          editingMessageIndex={editingMessageIndex}
          onEditMessage={setEditingMessageIndex}
          onUpdateSymbols={updateSymbolMessage}
          onCancelEdit={() => setEditingMessageIndex(null)}
          input={input}
          onInputChange={setInput}
          onSubmit={handleSend}
          voiceEnabled={voiceEnabled}
          isRecording={isRecording}
          hasRecording={hasRecording}
          startRecording={startRecording}
          stopRecording={stopRecording}
          sendRecording={sendRecording}
          discardRecording={discardRecording}
        />

        <BoardsAndTopicsSidebar
          isOpen={isBoardsOpen}
          onToggle={() => setIsBoardsOpen((open) => !open)}
          onStartActivity={startActivity}
          isStartingSession={isStartingSession}
        />

        {symbolView && (
          <LearningSymbolPanel
            filteredSymbols={filteredSymbols}
            coreWords={coreWords}
            symbolLoading={symbolLoading}
            symbolSearch={symbolSearch}
            onSearchChange={setSymbolSearch}
            selectedCategory={selectedCategory}
            onCategoryChange={setSelectedCategory}
            symbolUtterance={symbolUtterance}
            onAddSymbol={(symbol) => setSymbolUtterance((current) => [...current, symbol])}
            onRemoveSymbol={(index) => setSymbolUtterance((current) => current.filter((_, itemIndex) => itemIndex !== index))}
            onClearSymbols={() => setSymbolUtterance([])}
            onSendSymbols={() => { void sendSymbolUtterance(); }}
            onSpeakSymbols={(text) => {
              if (text) {
                tts.enqueue(text, {
                  rate: 0.9,
                  lang: currentLang === 'es' ? 'es-ES' : 'en-US',
                });
              }
            }}
            isLoading={isLoading}
            isStartingSession={isStartingSession}
          />
        )}
      </div>

      {lastSessionSummary && (
        <SessionSummaryModal summary={lastSessionSummary} onClose={clearSessionSummary} />
      )}
    </div>
  );
}
