import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useLearningStore } from '../store/learningStore';
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
import { useAssistantMessageSpeech } from '../hooks/useAssistantMessageSpeech';
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
  const { t, i18n } = useTranslation('learning');    const currentLang = i18n.language?.split('-')[0] || 'en';
  const symbolLanguage = currentLang === 'es' ? 'es' : 'en';

  const [input, setInput] = useState('');
  const [voiceEnabled, setVoiceEnabled] = useState(user?.settings?.voice_mode_enabled ?? true);
  const [showHistory, setShowHistory] = useState(false);
  const [selectedModeKey, setSelectedModeKey] = useState('practice');
  const [availableModes, setAvailableModes] = useState<Array<{ id: number; name: string; key: string; description: string; auto_ask_enabled?: boolean }>>([]);
  const [savedTopics, setSavedTopics] = useState<SavedTopic[]>([]);
  const [symbolView, setSymbolView] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState('');
  const [symbolItems, setSymbolItems] = useState<SymbolItem[]>([]);
  const [symbolLang, setSymbolLang] = useState('');
  const [symbolLoading, setSymbolLoading] = useState(false);
  const symbolViewWasOpenRef = useRef(false);
  const [symbolUtterance, setSymbolUtterance] = useState<SymbolItem[]>([]);
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [isBoardsOpen, setIsBoardsOpen] = useState(true);
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [sessionStartError, setSessionStartError] = useState<string | null>(null);
  const [providerNotice, setProviderNotice] = useState<string | null>(null);
  const skipInitialSpeech = useLearningStore((state) => state.skipInitialSpeech);
  const lastProviderHistoryLengthRef = useRef(0);
  const sessionStartErrorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    sessionTopic: t('topics.audioConversation'),
  });

  useEffect(() => {
    return () => {
      if (sessionStartErrorTimeoutRef.current) {
        clearTimeout(sessionStartErrorTimeoutRef.current);
      }
    };
  }, []);

  const showSessionStartError = useCallback((message: string, timeoutMs: number) => {
    if (sessionStartErrorTimeoutRef.current) {
      clearTimeout(sessionStartErrorTimeoutRef.current);
    }
    setSessionStartError(message);
    sessionStartErrorTimeoutRef.current = setTimeout(() => {
      setSessionStartError(null);
      sessionStartErrorTimeoutRef.current = null;
    }, timeoutMs);
  }, []);

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
      .then((response) => {
        // System modes (created_by null) keep the seeded English name in the
        // DB; translate by key so the dropdown matches the UI language.
        // Custom teacher modes always show their stored name.
        const modes = (response.data as Array<{
          id: number;
          name: string;
          key: string;
          description: string;
          auto_ask_enabled?: boolean;
          created_by?: number | null;
        }>).map((mode) => ({
          ...mode,
          name: mode.created_by == null
            ? t(`modes.${mode.key}`, mode.name)
            : mode.name,
        }));
        setAvailableModes(modes);
      })
      .catch((fetchError) => console.error('Failed to fetch learning modes', fetchError));
  }, [fetchBoards, t, user?.id]);

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
      // Auto-request the first adaptive question now that the session is
      // active. The welcome and the question are both spoken by
      // useAssistantMessageSpeech from the messages array, in order.
      void askNextQuestion();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('errors.unknownError');
      showSessionStartError(t('errors.sessionStartError', { error: message }), 8000);
    } finally {
      setIsStartingSession(false);
    }
  }, [askNextQuestion, fetchSessionHistory, selectedModeKey, sessionDifficulty, showSessionStartError, startSession, t, user]);

  const handleToggleHistory = useCallback(() => {
    const nextVisible = !showHistory;
    setShowHistory(nextVisible);
    if (nextVisible && user?.id) {
      void fetchSessionHistory(user.id);
    }
  }, [fetchSessionHistory, showHistory, user?.id]);

  // Toggle the voice input and persist it so it survives a reload.
  const handleToggleVoice = useCallback(() => {
    const next = !voiceEnabled;
    setVoiceEnabled(next);
    if (!user) return;
    api
      .put('/auth/preferences', { voice_mode_enabled: next })
      .then((response) => {
        useAuthStore.setState((state) => {
          if (!state.user) return state;
          return {
            user: {
              ...state.user,
              settings: response.data,
            },
          };
        });
      })
      .catch(() => {
        setVoiceEnabled(!next);
        addToast(t('learning:voiceSaveFailed'), 'error');
      });
  }, [addToast, t, user, voiceEnabled]);

  const handleNewConversation = useCallback(async () => {
    // The topic is an API value, not presentation text. Keep the canonical
    // backend key stable while the UI remains free to translate its label.
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
      showSessionStartError(t('errors.startSessionFirst'), 5000);
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
    // The send button is disabled whenever the utterance is empty, loading is
    // in progress, or a session is starting, so no guard is needed for those.
    if (!user) return;
    let sessionId = currentSession?.session_id;

    if (!sessionId) {
      setIsStartingSession(true);
      setSessionStartError(null);
      try {
        await startSession({
          topic: t('topics.symbolConversation'),
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
        showSessionStartError(t('errors.sessionStartError', { error: message }), 8000);
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
    const requestedLanguage = symbolLanguage;
    setSymbolLoading(true);
    try {
      const response = await api.get('/boards/symbols', {
        params: { limit: 1000, language: requestedLanguage },
      });
      setSymbolItems(dedupeLearningSymbols(response.data || []));
      setSymbolLang(requestedLanguage);
    } catch {
      setSymbolItems([]);
    } finally {
      setSymbolLoading(false);
    }
  }, [symbolLanguage]);

  // Prefetch the symbol library in the background as soon as the page
  // mounts so opening the symbol view never waits for the full fetch.
  // Re-runs on language change to keep the library aligned with the
  // active language.
  useEffect(() => {
    void fetchSymbols();
  }, [fetchSymbols]);

  useEffect(() => {
    if (!symbolView) {
      symbolViewWasOpenRef.current = false;
      return;
    }
    const justOpened = !symbolViewWasOpenRef.current;
    symbolViewWasOpenRef.current = true;
    setIsBoardsOpen(false);
    // The library is prefetched on mount; only fetch here once, when the
    // view opens and the data is missing for the current language (first
    // open before the prefetch finished, or a failed prefetch), and no
    // request is already in flight. Gating on the open transition prevents
    // a retry loop while the view stays open.
    if (justOpened && !symbolLoading && symbolLang !== symbolLanguage) {
      void fetchSymbols();
    }
  }, [fetchSymbols, symbolLoading, symbolLang, symbolLanguage, symbolView]);

  const filteredSymbols = useMemo(() => {
    let items = symbolItems;
    if (symbolSearch) {
      const query = symbolSearch.toLocaleLowerCase(symbolLanguage);
      items = items.filter((symbol) =>
        symbol.label.toLocaleLowerCase(symbolLanguage).includes(query) ||
        (symbol.keywords && symbol.keywords.toLocaleLowerCase(symbolLanguage).includes(query)),
      );
    }

    if (selectedCategory !== 'all') {
      items = selectedCategory === 'food'
        ? items.filter((symbol) => symbol.category === 'food' || symbol.category === 'drinks')
        : items.filter((symbol) => symbol.category === selectedCategory);
    }
    return items;
  }, [selectedCategory, symbolItems, symbolSearch, symbolLanguage]);

  const coreWords = useMemo(() => {
    const coreWordsByLanguage: Record<string, string[]> = {
      en: ['I', 'you', 'want', 'go', 'stop', 'help', 'yes', 'no', 'more', 'finished', 'like', 'eat', 'drink'],
      es: ['yo', 'tú', 'quiero', 'ir', 'parar', 'ayuda', 'sí', 'no', 'más', 'terminado', 'me gusta', 'comer', 'beber'],
    };
    const priorityWords = coreWordsByLanguage[symbolLanguage] || coreWordsByLanguage.en;
    // Case/accent-insensitive index so labels like "Yo" or "Me gusta" still
    // match the priority list and keep the panel populated for any casing.
    const priorityIndex = new Map(
      priorityWords.map((word, index) => [word.trim().toLocaleLowerCase(symbolLanguage), index]),
    );
    const byLabel = new Map<string, SymbolItem>();

    symbolItems
      .filter((symbol) => priorityIndex.has(symbol.label.trim().toLocaleLowerCase(symbolLanguage)))
      .forEach((symbol) => {
        const key = symbol.label.trim().toLocaleLowerCase(symbolLanguage);
        const existing = byLabel.get(key);
        if (!existing || (!existing.image_path && symbol.image_path)) {
          byLabel.set(key, symbol);
        }
      });

    return Array.from(byLabel.values()).sort(
      (a, b) =>
        (priorityIndex.get(a.label.trim().toLocaleLowerCase(symbolLanguage)) ?? 0) -
        (priorityIndex.get(b.label.trim().toLocaleLowerCase(symbolLanguage)) ?? 0),
    );
  }, [symbolLanguage, symbolItems]);

  useEffect(() => {
    const currentLength = providerHistory.length;
    if (currentLength <= lastProviderHistoryLengthRef.current || currentLength === 0) return;

    const last = providerHistory[currentLength - 1];
    lastProviderHistoryLengthRef.current = currentLength;
    const providerName =
      last.provider === 'openrouter'
        ? 'OpenRouter'
        : last.provider === 'groq'
          ? 'Groq'
          : last.provider === 'lmstudio'
            ? 'LM Studio'
            : 'Ollama';
    setProviderNotice(t('providerSwitched', { provider: providerName }));
    const timeoutId = setTimeout(() => setProviderNotice(null), 3000);
    return () => clearTimeout(timeoutId);
  }, [providerHistory, t]);

  // All assistant messages (welcome, questions, feedback) are spoken through
  // this one mechanism; no caller enqueues chat messages directly.
  useAssistantMessageSpeech({
    messages,
    sessionKey: currentSession?.session_id ?? null,
    enabled: voiceEnabled,
    skipExistingOnSessionChange: skipInitialSpeech,
  });

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
        onToggleVoice={handleToggleVoice}
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
                  lang: symbolLanguage === 'es' ? 'es-ES' : 'en-US',
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
