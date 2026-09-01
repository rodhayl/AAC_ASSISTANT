import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router';
import { useBoardStore } from '../store/boardStore';
import { useLearningStore } from '../store/learningStore';
import { CommunicationGrid } from '../components/board/CommunicationGrid';
import { SentenceStrip } from '../components/board/SentenceStrip';
import { Smartbar } from '../components/board/Smartbar';
import { CommunicationToolbar } from '../components/board/CommunicationToolbar';
import { KeyboardOverlay } from '../components/board/KeyboardOverlay';
import { CommunicationChat } from '../components/board/CommunicationChat';
import { SymbolSearchModal } from '../components/board/SymbolSearchModal';
import { PartnerOverlay } from '../components/board/PartnerOverlay';
import type { BoardSymbol } from '../types';
import { getBoardPlayabilityStatus } from './boardEditorUtils';
import { tts } from '../lib/tts';
import api from '../lib/api';
import { glossSymbolUtterance } from '../lib/gloss';
import {
  Search,
  LayoutGrid,
  Lock,
  ArrowLeft,
  Minimize2,
  Maximize2,
  PlusCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../store/authStore';
import { Button } from '../components/ui/button';
import { useToastStore } from '../store/toastStore';
import { BoardsAndTopicsSidebar } from '../components/learning/BoardsAndTopicsSidebar';
import { cn } from '../lib/utils';

const EMPTY_BOARD_SYMBOLS: BoardSymbol[] = [];

export function Communication() {
  const { t } = useTranslation(['boards', 'learning', 'common']);
  const [searchParams, setSearchParams] = useSearchParams();
  const boards = useBoardStore((state) => state.boards);
  const currentBoard = useBoardStore((state) => state.currentBoard);
  const fetchBoard = useBoardStore((state) => state.fetchBoard);
  const fetchBoards = useBoardStore((state) => state.fetchBoards);
  const fetchAssignedBoards = useBoardStore((state) => state.fetchAssignedBoards);
  const isListLoading = useBoardStore((state) => state.isListLoading);
  const isBoardLoading = useBoardStore((state) => state.isBoardLoading);
  const boardError = useBoardStore((state) => state.error);
  const assignedBoards = useBoardStore((state) => state.assignedBoards);
  const hasMore = useBoardStore((state) => state.hasMore);
  const page = useBoardStore((state) => state.page);
  const user = useAuthStore((state) => state.user);
  const submitSymbolAnswer = useLearningStore((state) => state.submitSymbolAnswer);
  const startSession = useLearningStore((state) => state.startSession);
  const resetSession = useLearningStore((state) => state.resetSession);
  const currentSession = useLearningStore((state) => state.currentSession);
  const isChatLoading = useLearningStore((state) => state.isLoading);
  const defaultLearningModeKey = user?.settings?.default_learning_mode || 'practice';

  const [activeBoardId, setActiveBoardId] = useState<number | null>(() => {
    const id = searchParams.get('boardId');
    return id ? parseInt(id) : null;
  });
  const [sentence, setSentence] = useState<BoardSymbol[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isKeyboardOpen, setIsKeyboardOpen] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isPartnerOpen, setIsPartnerOpen] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(user?.settings?.voice_mode_enabled ?? true);
  const [isBoardsOpen, setIsBoardsOpen] = useState(false);

  useEffect(() => {
    if (user?.settings?.voice_mode_enabled !== undefined) {
      setVoiceEnabled(user.settings.voice_mode_enabled);
    }
  }, [user?.settings?.voice_mode_enabled]);
  const [history, setHistory] = useState<number[]>([]);
  const addToast = useToastStore((state) => state.addToast);
  const [isStartingSession, setIsStartingSession] = useState(false);
  const lastClickRef = useRef<{ id: number; time: number } | null>(null);
  // Tracks the board id already mirrored into the URL so the effect below
  // does not re-fetch the board when setSearchParams re-renders with the same
  // value (previously every board open fetched twice).
  const syncedBoardIdRef = useRef<number | null>(null);

  // Communication sessions belong to the active board. Do not reuse a
  // learning session from another board (or from the Learning page), because
  // its welcome message would keep the old topic.
  useEffect(() => {
    if (!currentBoard || currentBoard.id !== activeBoardId) return;
    if (!currentSession) return;
    if (currentSession.board_id === currentBoard.id) return;
    resetSession();
  }, [activeBoardId, currentBoard, currentSession, resetSession]);

  // Helper to start activity from sidebar
  const handleStartActivity = async (topic: string, purpose: string, boardId?: number) => {
    if (!user) return;

    setIsStartingSession(true);

    try {
      await startSession({
        topic,
        purpose,
        difficulty: 'basic',
        board_id: boardId,
        mode_key: defaultLearningModeKey,
      }, user.id);
      addToast(t('common:sessionStarted'), 'success');
      // If a board was selected, we might want to switch to it? 
      // Current behavior: The sidebar allows selecting a board for the SESSION context.
      // If we want to VISUALLY switch to that board, we should:
      if (boardId) {
        setActiveBoardId(boardId);
      }
    } catch (err) {
      console.error("Failed to start session", err);
      addToast(t('common:sessionStartFailed'), 'error');
    } finally {
      setIsStartingSession(false);
    }
  };

  // Fetch available boards on mount
  useEffect(() => {
    if (!user) return;

    const loadBoards = async () => {
      if (user.user_type === 'student') {
        await fetchAssignedBoards(user.id, true);
      } else if (user.user_type === 'admin') {
        await fetchBoards(undefined, undefined, false, 1);
      } else {
        await fetchBoards(user.id, undefined, false, 1);
      }
    };

    loadBoards();
  }, [user, fetchBoards, fetchAssignedBoards]);

  const loadMore = () => {
    if (!isListLoading && hasMore && user && user.user_type !== 'student') {
      // Pagination currently only for fetchBoards, not fetchAssignedBoards
      fetchBoards(user.user_type === 'admin' ? undefined : user.id, undefined, false, page + 1);
    }
  };

  // Load active board details when selected
  useEffect(() => {
    if (activeBoardId && !isNaN(activeBoardId)) {
      if (syncedBoardIdRef.current !== activeBoardId) {
        syncedBoardIdRef.current = activeBoardId;
        fetchBoard(activeBoardId);
        setSearchParams({ boardId: activeBoardId.toString() });
      }
    } else {
      if (searchParams.has('boardId')) {
        syncedBoardIdRef.current = null;
        setSearchParams({});
      }
    }
  }, [activeBoardId, fetchBoard, setSearchParams, searchParams]);

  // TTS Status listener. The TTS queue is a module singleton that may already
  // be speaking when this page mounts (e.g. a symbol was tapped just before
  // navigating away and back). Initialize the local state from the queue's
  // current status and reset it together with the queue when a session closes
  // so `isSpeaking` can never be left stuck on `true`.
  useEffect(() => {
    const updateStatus = (status: 'idle' | 'speaking') => {
      setIsSpeaking(status === 'speaking');
    };
    setIsSpeaking(tts.getStatus() === 'speaking');
    const unsubscribe = tts.onStatusChange(updateStatus);
    return () => unsubscribe();
  }, []);

  // Handle fullscreen
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = () => {
    try {
      if (!document.fullscreenElement) {
        if (document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(err => {
            console.warn(`Fullscreen not supported or blocked: ${err.message}`);
          });
        }
      } else {
        if (document.exitFullscreen) {
          document.exitFullscreen().catch(err => console.warn(err));
        }
      }
    } catch (e) {
      console.warn("Fullscreen toggle failed", e);
    }
  };

  const handleSymbolClick = useCallback((symbol: BoardSymbol) => {
    // Check for ignore_repeats (debounce)
    const ignoreRepeatsMs = user?.settings?.ignore_repeats ?? 0;
    const now = Date.now();

    if (ignoreRepeatsMs > 0 && lastClickRef.current) {
      const { id, time } = lastClickRef.current;
      if (id === symbol.id && now - time < ignoreRepeatsMs) {
        return;
      }
    }

    lastClickRef.current = { id: symbol.id, time: now };

    if (symbol.linked_board_id) {
      if (activeBoardId) {
        setHistory(prev => [...prev, activeBoardId]);
      }
      setActiveBoardId(symbol.linked_board_id);
      return;
    }

    setSentence(prev => [...prev, symbol]);

    // Speak immediately on click if voice enabled
    if (voiceEnabled) {
      const text = symbol.custom_text || symbol.symbol.label;
      tts.enqueue(text, { key: symbol.id });
    }

    // Log symbol usage immediately
    api.post('/analytics/usage', {
      symbols: [{
        id: symbol.symbol.id,
        label: symbol.custom_text || symbol.symbol.label,
        category: symbol.symbol.category
      }],
      context_topic: "communication"
    }).catch(err => console.error('Failed to log usage:', err));
  }, [activeBoardId, voiceEnabled, user?.settings?.ignore_repeats]);

  const handleSpeakSentence = useCallback(async () => {
    if (sentence.length === 0) return;

    // 1. Speak the sentence if voice enabled
    if (voiceEnabled) {
      const text = sentence.map(s => s.custom_text || s.symbol.label).join('. ');
      tts.enqueue(text);
    }

    // 2. Log analytics (sentence usage)
    try {
      await api.post('/analytics/usage', {
        symbols: sentence.map(s => ({
          id: s.symbol.id,
          label: s.custom_text || s.symbol.label,
          category: s.symbol.category
        })),
        context_topic: "communication"
      });
    } catch (err) {
      console.error('Failed to log usage:', err);
    }
  }, [sentence, voiceEnabled]);

  const handleSendToChat = useCallback(async () => {
    if (sentence.length === 0 || isChatLoading) return;

    // Ensure chat is open
    if (!isChatOpen) setIsChatOpen(true);

    let activeSession = currentSession;

    // Start session if none exists
    if (!activeSession && user) {
      try {
        const boardTopic = currentBoard?.name?.trim() || t('topics.general');
        await startSession({
          topic: boardTopic,
          difficulty: "basic",
          purpose: "communication board",
          board_id: currentBoard?.id,
          mode_key: defaultLearningModeKey,
        }, user.id);

        // Get the newly created session
        activeSession = useLearningStore.getState().currentSession;
      } catch (e) {
        console.error("Failed to start session for chat", e);
        addToast(t('common:sessionStartFailed'), 'error');
        return;
      }
    }

    if (!activeSession) return;

    const symbolsForChat = sentence.map(s => ({
      id: s.symbol.id,
      label: s.custom_text || s.symbol.label,
      category: s.symbol.category,
      image_path: s.symbol.image_path
    }));

    const enriched_gloss = glossSymbolUtterance(symbolsForChat);
    const raw_gloss = symbolsForChat.map(s => s.label).join(' ');

    // Clear the strip immediately so the same phrase cannot be re-sent
    // accidentally while the request is in flight, but restore it (with an
    // error toast) when the send fails so the phrase is never lost.
    const phrase = sentence;
    setSentence([]);
    submitSymbolAnswer(activeSession.session_id, symbolsForChat, enriched_gloss, raw_gloss)
      .catch(err => {
        console.error('Failed to send to chat:', err);
        addToast(t('common:sendToChatFailed'), 'error');
        setSentence(phrase);
      });
  }, [sentence, currentSession, currentBoard, defaultLearningModeKey, isChatLoading, submitSymbolAnswer, isChatOpen, user, startSession, addToast, t]);

  // Topic context for the Smartbar. The board is the primary context in the
  // Communication surface, so the board name wins (a student on the
  // "Animales" board gets animal vocabulary even if an unrelated learning
  // session is still open). When no board is active, fall back to the active
  // session topic so the surface keeps the AI topic words and auto-generated
  // pictograms from the learning flow. No board/session -> no topic (plain
  // catalog suggestions, no LLM spend).
  const smartbarTopic = useMemo(() => {
    const boardName = currentBoard?.name?.trim();
    if (boardName) return boardName;
    return currentSession?.topic || null;
  }, [currentSession, currentBoard]);

  const handleHome = useCallback(() => {
    setActiveBoardId(null);
    setHistory([]);
    setSearchParams({});
  }, [setSearchParams]);

  const handleBack = useCallback(() => {
    if (history.length > 0) {
      const prevBoardId = history[history.length - 1];
      setHistory(prev => prev.slice(0, -1));
      setActiveBoardId(prevBoardId);
    } else {
      handleHome();
    }
  }, [history, handleHome]);

  // Cancel any pending speech and speak one message. All utterance helpers
  // (quick responses, attention phrase, keyboard/modal speak) share this.
  const speakText = useCallback((text: string) => {
    if (voiceEnabled) {
      tts.cancelAll();
      tts.enqueue(text);
    }
  }, [voiceEnabled]);

  const handleQuickResponse = useCallback(
    (text: string) => speakText(text),
    [speakText],
  );

  const handleAttention = useCallback(() => {
    speakText(t('common:attentionPhrase'));
  }, [speakText, t]);

  const handleSpeakText = useCallback(
    (text: string) => speakText(text),
    [speakText],
  );

  // Toggle the chat voice and persist the choice so it survives a reload.
  const handleVoiceToggle = useCallback(() => {
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
        addToast(t('common:voiceSaveFailed'), 'error');
      });
  }, [addToast, t, user, voiceEnabled]);

  const handleReorder = useCallback((fromIndex: number, toIndex: number) => {
    setSentence(prev => {
      const newSentence = [...prev];
      const [moved] = newSentence.splice(fromIndex, 1);
      newSentence.splice(toIndex, 0, moved);
      return newSentence;
    });
  }, []);

  const handleRemoveSentenceItem = useCallback((index: number) => {
    setSentence(prev => prev.filter((_, i) => i !== index));
  }, []);

  const handleClearSentence = useCallback(() => {
    setSentence([]);
  }, []);

  const handleBackspaceSentence = useCallback(() => {
    setSentence(prev => prev.slice(0, -1));
  }, []);

  const handleSelectSymbol = useCallback((symbol: BoardSymbol) => {
    setSentence(prev => [...prev, symbol]);
    if (voiceEnabled) {
      const text = symbol.custom_text || symbol.symbol.label;
      tts.enqueue(text, { key: symbol.id });
    }
  }, [voiceEnabled]);

  const availableBoards = useMemo(() => {
    // Students can have personal boards as well as assigned boards. Showing
    // only one collection made assigned boards disappear whenever the student
    // owned at least one board.
    return Array.from(
      new Map(
        [...boards, ...assignedBoards].map((board) => [board.id, board]),
      ).values(),
    );
  }, [assignedBoards, boards]);

  const filteredBoards = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return availableBoards;
    return availableBoards.filter((b) => {
      const name = (b.name || '').toLowerCase();
      const desc = (b.description || '').toLowerCase();
      return name.includes(q) || desc.includes(q);
    });
  }, [availableBoards, searchQuery]);
  const hasActiveSearch = searchQuery.trim().length > 0;

  // RENDER: Board Selection View
  if (!activeBoardId) {
    return (
      <div className="min-h-screen bg-transparent p-4 sm:p-6 space-y-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row gap-4 justify-between items-center mb-8">
            <div>
              <h1 className="text-2xl font-bold text-foreground">
                {t('common:communication')}
              </h1>
              <p className="text-muted-foreground mt-1">
                {t('common:selectBoardToStart')}
              </p>
            </div>

            <div className="relative w-full md:w-64">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <input
                id="board-search"
                name="board_search"
                type="text"
                placeholder={t('common:searchBoards')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
              />
            </div>
          </div>

          {isListLoading && availableBoards.length === 0 && !hasActiveSearch ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
            </div>
          ) : hasActiveSearch && filteredBoards.length === 0 ? (
            <div className="text-center py-12 bg-surface rounded-xl border border-border">
              <LayoutGrid className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground">
                {t('common:noBoardsMatchSearch')}
              </h3>
            </div>
          ) : !hasActiveSearch && availableBoards.length === 0 ? (
            <div className="text-center py-12 bg-surface rounded-xl border border-border">
              <LayoutGrid className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground">
                {t('common:noBoardsFound')}
              </h3>
              <p className="text-muted-foreground mt-2">
                {user?.user_type === 'student'
                  ? t('common:askTeacherForBoards')
                  : t('common:createBoardFirst')}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {filteredBoards.map((board) => {
                const status = getBoardPlayabilityStatus(
                  board,
                  board.symbols ?? EMPTY_BOARD_SYMBOLS,
                  board.playable_symbols_count,
                );
                const playable = status.playable;
                const symbolCount = typeof board.playable_symbols_count === 'number'
                  ? board.playable_symbols_count
                  : status.count;
                const { progress, needed } = status;

                return (
                  <button
                    key={board.id}
                    onClick={() => playable && setActiveBoardId(board.id)}
                    disabled={!playable}
                    className={`group relative glass-card rounded-xl text-left p-6 flex flex-col h-full ${playable
                      ? 'hover:shadow-lg dark:hover:shadow-neon hover:border-brand/50 cursor-pointer'
                      : 'opacity-80 cursor-not-allowed bg-background/50'
                      }`}
                  >
                    {!playable && (
                      <div className="absolute top-4 right-4 text-amber-700 dark:text-amber-400 z-10 flex flex-col items-end gap-1" title={t('common:boardTooEmpty')}>
                        <Lock className="w-5 h-5 drop-shadow-sm" />
                        <span className="text-xs font-bold bg-amber-100 dark:bg-amber-900/60 px-2 py-0.5 rounded shadow-sm border border-amber-200 dark:border-amber-800/50">
                          {progress}%
                        </span>
                      </div>
                    )}

                    <div className={`mb-4 p-3 rounded-xl w-fit transition-transform duration-300 ${playable ? 'bg-brand/10 group-hover:scale-110' : 'bg-muted'}`}>
                      <div className={`w-12 h-12 rounded-lg flex items-center justify-center shadow-inner ${playable ? 'bg-gradient-to-br from-indigo-500 via-blue-500 to-purple-500' : 'bg-muted-foreground'}`}>
                        <LayoutGrid className="w-6 h-6 text-white" />
                      </div>
                    </div>

                    <h3 className="text-lg font-bold text-foreground mb-2 group-hover:text-brand transition-colors">
                      {board.name}
                    </h3>

                    {board.description && (
                      <p className="text-sm text-muted-foreground line-clamp-2 mb-4 flex-1">
                        {board.description}
                      </p>
                    )}

                    {!playable && (
                      <div className="mt-auto mb-4">
                        <p className="text-xs text-amber-700 dark:text-amber-400 font-bold mb-2 flex items-center gap-1">
                          <PlusCircle className="w-3 h-3" />
                          {needed === 1
                            ? t('common:addOneMoreSymbol')
                            : t('common:addMoreSymbolsToUnlock', { count: needed })}
                        </p>
                        <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden shadow-inner">
                          <div
                            className="h-full bg-gradient-to-r from-amber-400 to-amber-600 transition-all duration-700 ease-out shadow-sm"
                            style={{ width: `${Math.min(100, progress)}%` }}
                          />
                        </div>
                      </div>
                    )}

                    <div className="mt-auto pt-4 border-t border-border w-full flex justify-between items-center">
                      <span className={`text-sm font-medium flex items-center ${playable ? 'text-brand' : 'text-muted-foreground'}`}>
                        {playable ? t('common:openBoard') : t('common:boardLocked')}
                        {playable && <ArrowLeft className="w-4 h-4 ml-1 rotate-180" />}
                      </span>
                      <span className="text-xs text-muted-foreground font-medium">
                        {symbolCount} {symbolCount === 1 ? t('common:symbol') : t('common:symbols')}
                      </span>
                    </div>
                  </button>
                );
              })}

              {/* Load More Button */}
              {hasMore && !isListLoading && user?.user_type !== 'student' && (
                <div className="col-span-full flex justify-center py-6">
                  <button
                    onClick={loadMore}
                    className="px-6 py-2 bg-surface border border-border rounded-lg shadow-sm text-sm font-medium text-foreground hover:bg-surface-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand"
                  >
                    {t('common:loadMore')}
                  </button>
                </div>
              )}
              {isListLoading && (
                <div className="col-span-full flex justify-center py-6">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand"></div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // RENDER: Active Board View (Communication Mode)
  if (isBoardLoading || !currentBoard) {
    // A failed board fetch must not leave the user staring at an endless
    // spinner: offer a retry and a way back to the board list.
    if (!isBoardLoading && !currentBoard && activeBoardId && boardError) {
      return (
        <div className="flex items-center justify-center h-screen bg-background p-4">
          <div className="max-w-md w-full text-center bg-surface rounded-xl border border-red-200 dark:border-red-900/60 p-8 shadow-lg">
            <div className="text-red-600 dark:text-red-400 text-lg font-bold mb-2">
              {t('common:boardLoadFailed')}
            </div>
            <p className="text-sm text-muted-foreground mb-6 break-words">{boardError}</p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                onClick={() => fetchBoard(activeBoardId, true)}
              >
                {t('common:retry')}
              </Button>
              <Button
                variant="outline"
                onClick={handleHome}
              >
                {t('common:backToBoards')}
              </Button>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand"></div>
      </div>
    );
  }

  const rows = currentBoard.grid_rows ?? 4;
  const cols = currentBoard.grid_cols ?? 5;

  return (
    <div className="flex h-full w-full bg-background overflow-hidden relative">
      {/* Left Panel: Board & Sentence Strip */}
      <div className={cn('relative flex h-full min-h-0 min-w-0 flex-1 flex-col transition-all duration-300', isChatOpen && 'lg:mr-0')}>
        {/* Header */}
        <header className="glass-panel border-b border-border px-4 py-2 flex items-center justify-between shrink-0 z-10 h-14">
          <h1 className="text-lg font-bold text-foreground truncate">
            {currentBoard.name}
          </h1>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleFullscreen}
              className="p-2 hover:bg-surface-hover rounded-lg text-muted-foreground transition-colors"
              title={isFullscreen ? t('exitFullscreen') : t('enterFullscreen')}
            >
              {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
            </button>
          </div>
        </header>

        {/* Sentence Strip */}
        <div className="shrink-0 z-20">
          <SentenceStrip
            symbols={sentence}
            onRemove={handleRemoveSentenceItem}
            onClear={handleClearSentence}
            onBackspace={handleBackspaceSentence}
            onSpeak={handleSpeakSentence}
            onSpeakItem={handleSpeakText}
            onReorder={handleReorder}
            onAskAI={handleSendToChat}
            isSpeaking={isSpeaking}
          />
        </div>

        {/* Smartbar (Suggestions) */}
        <Smartbar
          currentSentence={sentence}
          onSelectSymbol={handleSelectSymbol}
          boardId={currentBoard?.id}
          topic={smartbarTopic}
        />

        {/* Grid Area */}
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-2 custom-scrollbar relative min-h-0 w-full">
          <CommunicationGrid
            rows={rows}
            cols={cols}
            symbols={currentBoard.symbols ?? EMPTY_BOARD_SYMBOLS}
            onSymbolClick={handleSymbolClick}
          />
        </main>

        {/* Communication Toolbar (Bottom) */}
        <div className="shrink-0 z-30 glass-panel border-t border-border w-full">
          <CommunicationToolbar
            onHome={handleHome}
            onBack={handleBack}
            onToggleKeyboard={() => setIsKeyboardOpen(prev => !prev)}
            onToggleChat={() => setIsChatOpen(prev => !prev)}
            onSearch={() => setIsSearchOpen(true)}
            onContext={() => setIsBoardsOpen(prev => !prev)}
            onPartnerMic={() => setIsPartnerOpen(true)}
            onQuickResponse={handleQuickResponse}
            onAttention={handleAttention}
            isKeyboardOpen={isKeyboardOpen}
            isChatOpen={isChatOpen}
            canGoBack={history.length > 0}
          />
        </div>
      </div>

      {/* Boards & Topics Sidebar */}
      <BoardsAndTopicsSidebar
        isOpen={isBoardsOpen}
        onToggle={() => setIsBoardsOpen(!isBoardsOpen)}
        onStartActivity={handleStartActivity}
        isStartingSession={isStartingSession}
        className="h-full border-l border-border"
      />

      {/* Right Panel: Chat Interface */}
      <div
        className={`
          fixed inset-y-0 right-0 z-40 w-full sm:w-96 lg:w-[35%] glass-panel shadow-2xl transform transition-transform duration-300 ease-in-out
          lg:relative lg:translate-x-0 lg:shadow-none lg:border-l lg:border-border/20
          ${isChatOpen ? 'translate-x-0' : 'translate-x-full lg:hidden'}
        `}
      >
        <CommunicationChat
          voiceEnabled={voiceEnabled}
          onVoiceToggle={handleVoiceToggle}
          boardId={currentBoard.id}
          boardName={currentBoard.name}
        />
      </div>

      {/* Modals and Overlays */}
      <KeyboardOverlay
        isOpen={isKeyboardOpen}
        onClose={() => setIsKeyboardOpen(false)}
        onSpeak={handleSpeakText}
      />

      <PartnerOverlay
        isOpen={isPartnerOpen}
        onClose={() => setIsPartnerOpen(false)}
      />

      <SymbolSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelectSymbol={handleSelectSymbol}
      />
    </div>
  );
}
