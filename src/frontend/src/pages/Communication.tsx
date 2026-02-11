import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useBoardStore } from '../store/boardStore';
import { useLearningStore } from '../store/learningStore';
import { SymbolCard } from '../components/board/SymbolCard';
import { SentenceStrip } from '../components/board/SentenceStrip';
import { Smartbar } from '../components/board/Smartbar';
import { CommunicationToolbar } from '../components/board/CommunicationToolbar';
import { KeyboardOverlay } from '../components/board/KeyboardOverlay';
import { CommunicationChat } from '../components/board/CommunicationChat';
import { SymbolSearchModal } from '../components/board/SymbolSearchModal';
import { PartnerOverlay } from '../components/board/PartnerOverlay';
import type { BoardSymbol } from '../types';
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
import { useToastStore } from '../store/toastStore';
import { BoardsAndTopicsSidebar } from '../components/learning/BoardsAndTopicsSidebar';

export function Communication() {
  const { t } = useTranslation('boards');
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    boards,
    currentBoard,
    fetchBoard,
    fetchBoards,
    fetchAssignedBoards,
    isLoading,
    assignedBoards,
    hasMore,
    page
  } = useBoardStore();
  const { user } = useAuthStore();
  const {
    submitSymbolAnswer,
    startSession,
    currentSession,
    isLoading: isChatLoading
  } = useLearningStore();

  const [activeBoardId, setActiveBoardId] = useState<number | null>(() => {
    const id = searchParams.get('boardId');
    return id ? parseInt(id) : null;
  });
  // const [currentFolderId, setCurrentFolderId] = useState<number | null>(null); // Unused state
  // const [viewMode, setViewMode] = useState<'grid' | 'folder'>('grid'); // Unused state
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
  const [history, setHistory] = useState<number[]>([]);
  const { addToast } = useToastStore();
  const [isStartingSession, setIsStartingSession] = useState(false);
  const lastClickRef = useRef<{ id: number; time: number } | null>(null);

  // Helper to start activity from sidebar
  const handleStartActivity = async (topic: string, purpose: string, boardId?: number) => {
    if (!user) return;

    setIsStartingSession(true);

    try {
      await startSession({
        topic,
        purpose,
        difficulty: 'basic',
        board_id: boardId
      }, user.id);
      addToast(t('sessionStarted', 'Session started'), 'success');
      // If a board was selected, we might want to switch to it? 
      // Current behavior: The sidebar allows selecting a board for the SESSION context.
      // If we want to VISUALLY switch to that board, we should:
      if (boardId) {
        setActiveBoardId(boardId);
      }
    } catch (err) {
      console.error("Failed to start session", err);
      addToast(t('sessionStartFailed', 'Failed to start session'), 'error');
    } finally {
      setIsStartingSession(false);
    }
  };

  // Helper to check if board has enough symbols (at least 50% capacity)
  type BoardPlayableInfo = {
    grid_rows?: number;
    grid_cols?: number;
    playable_symbols_count?: number;
    symbols?: Array<{
      is_visible: boolean;
      custom_text?: string;
      symbol?: { label?: string };
    }>;
  };

  const isBoardPlayable = useCallback((board: BoardPlayableInfo) => {
    const rows = board.grid_rows || 4;
    const cols = board.grid_cols || 5;
    const capacity = rows * cols;

    // Use playable_symbols_count if available (from backend), otherwise count symbols array
    let symbolCount = 0;
    if (typeof board.playable_symbols_count === 'number') {
      symbolCount = board.playable_symbols_count;
    } else if (board.symbols) {
      symbolCount = board.symbols.filter(s =>
        s.is_visible && (s.custom_text || s.symbol?.label)
      ).length;
    }

    // Avoid division by zero
    if (capacity === 0) return false;

    const fillRate = symbolCount / capacity;
    return fillRate >= 0.5;
  }, []);

  // Fetch available boards on mount
  useEffect(() => {
    if (!user) return;

    const loadBoards = async () => {
      if (user.user_type === 'student') {
        await fetchAssignedBoards(user.id, true);
      } else if (user.user_type === 'admin') {
        await fetchBoards(undefined, searchQuery, false, 1);
      } else {
        await fetchBoards(user.id, searchQuery, false, 1);
      }
    };

    loadBoards();
  }, [user, fetchBoards, fetchAssignedBoards, searchQuery]);

  const loadMore = () => {
    if (!isLoading && hasMore && user && user.user_type !== 'student') {
      // Pagination currently only for fetchBoards, not fetchAssignedBoards
      fetchBoards(user.user_type === 'admin' ? undefined : user.id, searchQuery, false, page + 1);
    }
  };

  // Load active board details when selected
  useEffect(() => {
    if (activeBoardId) {
      if (!isNaN(activeBoardId)) {
        fetchBoard(activeBoardId);
        setSearchParams({ boardId: activeBoardId.toString() });
      }
    } else {
      if (searchParams.has('boardId')) {
        setSearchParams({});
      }
    }
  }, [activeBoardId, fetchBoard, setSearchParams, searchParams]);

  // TTS Status listener
  useEffect(() => {
    const updateStatus = (status: 'idle' | 'speaking') => {
      setIsSpeaking(status === 'speaking');
    };
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
        await startSession({
          topic: "general conversation",
          difficulty: "basic",
          purpose: "communication board"
        }, user.id);

        // Get the newly created session
        activeSession = useLearningStore.getState().currentSession;
      } catch (e) {
        console.error("Failed to start session for chat", e);
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

    submitSymbolAnswer(activeSession.session_id, symbolsForChat, enriched_gloss, raw_gloss)
      .catch(err => console.error('Failed to send to chat:', err));
  }, [sentence, currentSession, isChatLoading, submitSymbolAnswer, isChatOpen, user, startSession]);

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

  const handleQuickResponse = useCallback((text: string) => {
    if (voiceEnabled) {
      tts.cancelAll();
      tts.enqueue(text);
    }
  }, [voiceEnabled]);

  const handleAttention = useCallback(() => {
    if (voiceEnabled) {
      tts.cancelAll();
      tts.enqueue(t('attentionPhrase', 'Excuse me!'));
    }
  }, [t, voiceEnabled]);

  const handleSpeakText = useCallback((text: string) => {
    if (voiceEnabled) {
      tts.cancelAll();
      tts.enqueue(text);
    }
  }, [voiceEnabled]);

  const handleReorder = useCallback((fromIndex: number, toIndex: number) => {
    setSentence(prev => {
      const newSentence = [...prev];
      const [moved] = newSentence.splice(fromIndex, 1);
      newSentence.splice(toIndex, 0, moved);
      return newSentence;
    });
  }, []);

  const availableBoards = useMemo(() => {
    return boards.length > 0 ? boards : assignedBoards;
  }, [boards, assignedBoards]);

  const filteredBoards = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return availableBoards;
    return availableBoards.filter((b) => {
      const name = (b.name || '').toLowerCase();
      const desc = (b.description || '').toLowerCase();
      return name.includes(q) || desc.includes(q);
    });
  }, [availableBoards, searchQuery]);

  // RENDER: Board Selection View
  if (!activeBoardId) {
    return (
      <div className="min-h-screen bg-transparent p-4 sm:p-6 space-y-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row gap-4 justify-between items-center mb-8">
            <div>
              <h1 className="text-2xl font-bold text-primary">
                {t('communication', 'Communication')}
              </h1>
              <p className="text-gray-500 dark:text-gray-400 mt-1">
                {t('selectBoardToStart', 'Select a board to start communicating')}
              </p>
            </div>

            <div className="relative w-full md:w-64">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
              <input
                id="board-search"
                name="board_search"
                type="text"
                placeholder={t('searchBoards', 'Search boards...')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>
          </div>

          {isLoading && availableBoards.length === 0 ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
            </div>
          ) : availableBoards.length === 0 ? (
            <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
              <LayoutGrid className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                {t('noBoardsFound', 'No boards found')}
              </h3>
              <p className="text-gray-500 dark:text-gray-400 mt-2">
                {user?.user_type === 'student'
                  ? t('askTeacherForBoards', 'Ask your teacher to assign you a board.')
                  : t('createBoardFirst', 'Create a board in the Boards section first.')}
              </p>
            </div>
          ) : filteredBoards.length === 0 ? (
            <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
              <LayoutGrid className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                {t('noBoardsMatchSearch', 'No boards match your search')}
              </h3>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {filteredBoards.map((board) => {
                const playable = isBoardPlayable(board);
                // Calculate symbol count for display
                const symbolCount = typeof board.playable_symbols_count === 'number'
                  ? board.playable_symbols_count
                  : (board.symbols?.filter(s => s.is_visible).length || 0);

                const capacity = (board.grid_rows || 4) * (board.grid_cols || 5);
                const threshold = Math.ceil(capacity * 0.5);
                const progress = Math.round((symbolCount / threshold) * 100);
                const needed = Math.max(0, threshold - symbolCount);

                return (
                  <button
                    key={board.id}
                    onClick={() => playable && setActiveBoardId(board.id)}
                    disabled={!playable}
                    className={`group relative glass-card rounded-xl text-left p-6 flex flex-col h-full ${playable
                      ? 'hover:shadow-lg dark:hover:shadow-neon hover:border-brand/50 cursor-pointer'
                      : 'opacity-80 cursor-not-allowed bg-gray-50/50 dark:bg-surface/20'
                      }`}
                  >
                    {!playable && (
                      <div className="absolute top-4 right-4 text-amber-600 dark:text-amber-400 z-10 flex flex-col items-end gap-1" title={t('boardTooEmpty', 'Board needs at least 50% symbols to be used')}>
                        <Lock className="w-5 h-5 drop-shadow-sm" />
                        <span className="text-xs font-bold bg-amber-100 dark:bg-amber-900/60 px-2 py-0.5 rounded shadow-sm border border-amber-200 dark:border-amber-800/50">
                          {progress}%
                        </span>
                      </div>
                    )}

                    <div className={`mb-4 p-3 rounded-xl w-fit transition-transform duration-300 ${playable ? 'bg-indigo-50 dark:bg-indigo-900/30 group-hover:scale-110' : 'bg-gray-100 dark:bg-gray-700'}`}>
                      <div className={`w-12 h-12 rounded-lg flex items-center justify-center shadow-inner ${playable ? 'bg-gradient-to-br from-indigo-500 via-blue-500 to-purple-500' : 'bg-gray-400'}`}>
                        <LayoutGrid className="w-6 h-6 text-white" />
                      </div>
                    </div>

                    <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {board.name}
                    </h3>

                    {board.description && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-4 flex-1">
                        {board.description}
                      </p>
                    )}

                    {!playable && (
                      <div className="mt-auto mb-4">
                        <p className="text-xs text-amber-600 dark:text-amber-500 font-bold mb-2 flex items-center gap-1">
                          <PlusCircle className="w-3 h-3" />
                          {needed === 1
                            ? t('addOneMoreSymbol', 'Add 1 more symbol to unlock')
                            : t('addMoreSymbolsToUnlock', 'Add {{count}} more symbols to unlock', { count: needed })}
                        </p>
                        <div className="h-1.5 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden shadow-inner">
                          <div
                            className="h-full bg-gradient-to-r from-amber-400 to-amber-600 transition-all duration-700 ease-out shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                            style={{ width: `${Math.min(100, progress)}%` }}
                          />
                        </div>
                      </div>
                    )}

                    <div className="mt-auto pt-4 border-t border-gray-100 dark:border-gray-700 w-full flex justify-between items-center">
                      <span className={`text-sm font-medium flex items-center ${playable ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400'}`}>
                        {playable ? t('openBoard', 'Open Board') : t('boardLocked', 'Board Locked')}
                        {playable && <ArrowLeft className="w-4 h-4 ml-1 rotate-180" />}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                        {symbolCount} {symbolCount === 1 ? t('symbol', 'symbol') : t('symbols', 'symbols')}
                      </span>
                    </div>
                  </button>
                );
              })}

              {/* Load More Button */}
              {hasMore && !isLoading && user?.user_type !== 'student' && (
                <div className="col-span-full flex justify-center py-6">
                  <button
                    onClick={loadMore}
                    className="px-6 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                  >
                    {t('loadMore', 'Load More')}
                  </button>
                </div>
              )}
              {isLoading && (
                <div className="col-span-full flex justify-center py-6">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // RENDER: Active Board View (Communication Mode)
  if (isLoading || !currentBoard) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50 dark:bg-gray-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  const rows = currentBoard.grid_rows ?? 4;
  const cols = currentBoard.grid_cols ?? 5;

  return (
    <div className="flex h-full w-full bg-transparent overflow-hidden relative">
      {/* Left Panel: Board & Sentence Strip */}
      <div className={`flex flex-col flex-1 h-full min-h-0 transition-all duration-300 ${isChatOpen ? 'lg:mr-0' : ''} relative`}>
        {/* Header */}
        <header className="glass-panel border-b border-border dark:border-white/5 px-4 py-2 flex items-center justify-between shrink-0 z-10 h-14">
          <h1 className="text-lg font-bold text-primary truncate">
            {currentBoard.name}
          </h1>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleFullscreen}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-600 dark:text-gray-300 transition-colors"
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
            onRemove={(idx) => setSentence(prev => prev.filter((_, i) => i !== idx))}
            onClear={() => setSentence([])}
            onBackspace={() => setSentence(prev => prev.slice(0, -1))}
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
          onSelectSymbol={(symbol) => {
            setSentence(prev => [...prev, symbol]);
            if (voiceEnabled) {
              const text = symbol.custom_text || symbol.symbol.label;
              tts.enqueue(text, { key: symbol.id });
            }
          }}
          boardId={currentBoard?.id}
        />

        {/* Grid Area */}
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-2 custom-scrollbar relative min-h-0 w-full">
          <div
            className="grid gap-2 mx-auto max-w-7xl pb-2"
            style={{
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
              minHeight: '100%'
            }}
          >
            {Array.from({ length: rows }).map((_, row) => (
              Array.from({ length: cols }).map((_, col) => {
                const symbol = currentBoard.symbols?.find(s => s.position_x === col && s.position_y === row);
                return (
                  <div key={`${col}-${row}`} className="w-full h-full min-h-[60px] sm:min-h-[70px] aspect-[1/0.8]">
                    {symbol ? (
                      <SymbolCard
                        boardSymbol={symbol}
                        onClick={handleSymbolClick}
                      />
                    ) : (
                      <div className="w-full h-full bg-gray-200/10 dark:bg-gray-800/10 rounded-xl border border-dashed border-gray-300/20 dark:border-gray-700/20" />
                    )}
                  </div>
                );
              })
            ))}
          </div>
        </main>

        {/* Communication Toolbar (Bottom) */}
        <div className="shrink-0 z-30 glass-panel border-t border-border dark:border-white/5 w-full">
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
        className="h-full border-l border-gray-200 dark:border-gray-700"
      />

      {/* Right Panel: Chat Interface */}
      <div
        className={`
          fixed inset-y-0 right-0 z-40 w-full sm:w-96 lg:w-[35%] glass-panel shadow-2xl transform transition-transform duration-300 ease-in-out
          lg:relative lg:translate-x-0 lg:shadow-none lg:border-l lg:border-border dark:border-white/5
          ${isChatOpen ? 'translate-x-0' : 'translate-x-full lg:hidden'}
        `}
      >
        <CommunicationChat
          voiceEnabled={voiceEnabled}
          onVoiceToggle={() => setVoiceEnabled(prev => !prev)}
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
        onSelectSymbol={(symbol) => {
          setSentence(prev => [...prev, symbol]);
          if (voiceEnabled) {
            const text = symbol.custom_text || symbol.symbol.label;
            tts.enqueue(text, { key: symbol.id });
          }
        }}
      />
    </div>
  );
}
