import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Bot, Send, Sparkles, Mic, Square, Volume2, VolumeX, Cpu, Cloud, Grid as GridIcon, Edit, Search, X, Trash2 } from 'lucide-react';
import { useLearningStore, stripReasoning } from '../store/learningStore';
import { useAuthStore } from '../store/authStore';
import { useBoardStore } from '../store/boardStore';
import { loadTopicsForUser, saveTopicsForUser } from '../lib/learningTopics';
import { type SavedTopic } from '../lib/learningTopics';
import api from '../lib/api';
import { assetUrl } from '../lib/utils';
import { SymbolMessageEditor } from '../components/SymbolMessageEditor';
import { tts } from '../lib/tts';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../store/toastStore';
import { Smartbar } from '../components/board/Smartbar';
import type { BoardSymbol } from '../types';
import { BoardsAndTopicsSidebar } from '../components/learning/BoardsAndTopicsSidebar';

// Helper to convert input text to pseudo-BoardSymbols for Smartbar context
const inputToSymbols = (text: string): BoardSymbol[] => {
  if (!text.trim()) return [];
  return text.trim().split(/\s+/).map((word, idx) => ({
    id: idx,
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
    }
  }));
};

type SymbolItem = { id: number; label: string; category: string; image_path?: string; keywords?: string };

const dedupeSymbolItems = (items: SymbolItem[]): SymbolItem[] => {
  const map = new Map<string, SymbolItem>();
  const norm = (s: string) => s.trim().toLowerCase();

  for (const item of items) {
    const label = norm(item.label || '');
    if (!label) continue;

    const key = `${label}|${norm(item.category || '')}`;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, item);
      continue;
    }

    if (!existing.image_path && item.image_path) {
      map.set(key, item);
    }
  }

  return Array.from(map.values());
};

export function Learning() {
  const {
    messages,
    isLoading,
    error,
    clearError,
    currentSession,
    sessionHistory,
    isLoadingHistory,
    startSession,
    submitAnswer,
    submitVoiceAnswer,
    submitSymbolAnswer,
    fetchSessionHistory,
    loadSession,
    showAdminReasoning,
    setShowAdminReasoning
  } = useLearningStore();
  const { user } = useAuthStore();
  const { addToast } = useToastStore();
  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(user?.settings?.voice_mode_enabled ?? true);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (user?.settings?.voice_mode_enabled !== undefined) {
      setVoiceEnabled(user.settings.voice_mode_enabled);
    }
  }, [user?.settings?.voice_mode_enabled]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const lastSpokenMessageRef = useRef<string | null>(null);
  const [selectedModeKey, setSelectedModeKey] = useState<string>('practice');
  const [availableModes, setAvailableModes] = useState<Array<{ id: number; name: string; key: string; description: string }>>([]);
  const { fetchBoards } = useBoardStore();

  const [savedTopics, setSavedTopics] = useState<SavedTopic[]>([]);
  const [symbolView, setSymbolView] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState('');
  const [symbolItems, setSymbolItems] = useState<SymbolItem[]>([]);
  const [symbolLoading, setSymbolLoading] = useState(false);
  const [hasRecording, setHasRecording] = useState(false);
  const [symbolUtterance, setSymbolUtterance] = useState<Array<{ id: number; label: string; category?: string; image_path?: string }>>([]);
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [isBoardsOpen, setIsBoardsOpen] = useState(true); // Collapsible boards panel
  const { t, i18n } = useTranslation('learning');
  const currentLang = i18n.language?.split('-')[0] || 'en';

  const isAdmin = user?.user_type === 'admin';

  // Fix #1: Add loading state for session start
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [sessionStartError, setSessionStartError] = useState<string | null>(null);

  // Load/save topics per user from localStorage via helper
  useEffect(() => {
    if (!user?.id) return;
    setSavedTopics(loadTopicsForUser(user.id));
  }, [user?.id]);

  useEffect(() => {
    if (!user?.id) return;
    saveTopicsForUser(user.id, savedTopics);
  }, [savedTopics, user?.id]);

  useEffect(() => {
    if (user?.id) {
      fetchBoards(user.id);
      // Fetch learning modes
      api.get('/learning-modes/')
        .then(res => setAvailableModes(res.data))
        .catch(err => console.error("Failed to fetch learning modes", err));
    }
  }, [user?.id, fetchBoards]);

  useEffect(() => {
    if (user?.id) {
      fetchSessionHistory(user.id);
    }
  }, [user?.id, fetchSessionHistory]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    clearError();

    // Fix #3: Check for active session before sending
    if (!currentSession) {
      setSessionStartError(t('errors.startSessionFirst'));
      setTimeout(() => setSessionStartError(null), 5000);
      return;
    }

    const answer = input;
    setInput('');

    await submitAnswer(currentSession.session_id, answer);
  };

  const startRecording = async () => {
    try {
      if (!currentSession && user) {
        await startSession({ topic: 'audio conversation', purpose: 'voice', difficulty: 'basic' }, user.id);
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        setHasRecording(true);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Error accessing microphone:', err);
      addToast(t('errors.microphoneAccess'), 'error');
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
    if (!currentSession || chunksRef.current.length === 0 || isLoading) {
      return;
    }
    const audioBlob = new Blob(chunksRef.current, { type: 'audio/wav' });
    // Keep hasRecording true while we are submitting so the UI
    // can show a "transcribing" state tied to isLoading.
    await submitVoiceAnswer(currentSession.session_id, audioBlob);
    chunksRef.current = [];
    setHasRecording(false);
  };

  const clearSymbolUtterance = () => setSymbolUtterance([]);

  const removeSymbolAt = (index: number) => {
    setSymbolUtterance(prev => prev.filter((_, i) => i !== index));
  };

  // Category color mapping for visual organization
  const getCategoryColor = (category?: string): string => {
    const colors: Record<string, string> = {
      'action': 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',
      'object': 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800',
      'person': 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800',
      'feeling': 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300 border-pink-200 dark:border-pink-800',
      'place': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800',
      'question': 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-800',
      'ARASAAC': 'bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 border-teal-200 dark:border-teal-800',
    };
    return colors[category || ''] || 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border-indigo-100 dark:border-indigo-800';
  };

  // Template-based glossing patterns for common AAC constructions
  interface GlossTemplate {
    pattern: RegExp;
    transform: (matches: RegExpMatchArray) => string;
  }

  const glossTemplates: GlossTemplate[] = [
    // Pronoun + want/need + object â†’ "I want X" / "I need X"
    {
      pattern: /^(I|me|my)\s+(want|need)\s+(.+)$/i,
      transform: (matches) => `I ${matches[2].toLowerCase()} ${matches[3]}.`
    },
    // Subject + action verb + object â†’ Proper capitalization
    {
      pattern: /^(.+?)\s+(eat|drink|play|go|help|like|love|see)\s+(.+)$/i,
      transform: (matches) => {
        const subj = matches[1].charAt(0).toUpperCase() + matches[1].slice(1).toLowerCase();
        return `${subj} ${matches[2].toLowerCase()} ${matches[3]}.`;
      }
    },
    // Question words â†’ Add question mark
    {
      pattern: /^(what|where|when|who|why|how)\s+(.+)$/i,
      transform: (matches) => {
        const qWord = matches[1].charAt(0).toUpperCase() + matches[1].slice(1).toLowerCase();
        return `${qWord} ${matches[2].toLowerCase()}?`;
      }
    },
    // Single feeling word â†’ "I feel X"
    {
      pattern: /^(happy|sad|angry|tired|hungry|thirsty|excited|scared|bored)$/i,
      transform: (matches) => `I feel ${matches[1].toLowerCase()}.`
    },
    // Pronoun + feeling â†’ "I feel X"
    {
      pattern: /^(I|me)\s+(happy|sad|angry|tired|hungry|thirsty|excited|scared)$/i,
      transform: (matches) => `I feel ${matches[2].toLowerCase()}.`
    }
  ];

  const glossSymbolUtterance = (symbols: Array<{ label: string; category?: string }>): string => {
    if (!symbols.length) return '';
    const joined = symbols.map(s => s.label.trim()).filter(Boolean).join(' ');
    if (!joined) return '';

    // Try template matching for enhanced glossing
    for (const template of glossTemplates) {
      const match = joined.match(template.pattern);
      if (match) {
        return template.transform(match);
      }
    }

    // Fallback: basic capitalization + punctuation
    const capped = joined.charAt(0).toUpperCase() + joined.slice(1);
    const needsPeriod = !/[.!?]$/.test(capped);
    return needsPeriod ? `${capped}.` : capped;
  };

  const sendSymbolUtterance = async () => {
    if (symbolUtterance.length === 0 || isLoading) return;
    let sessionId = currentSession?.session_id;

    // Fix #2: Add timeout and loading state for auto-started sessions
    if (!sessionId) {
      if (!user) return;

      setIsStartingSession(true);
      setSessionStartError(null);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, 30000); // 30 second timeout

      try {
        await startSession({
          topic: 'symbol conversation',
          purpose: 'aac symbols',
          difficulty: 'basic'
        }, user.id);

        clearTimeout(timeoutId);
        sessionId = useLearningStore.getState().currentSession?.session_id ?? undefined;

        if (!sessionId) {
          setSessionStartError(t('errors.sessionStartFailed'));
          setIsStartingSession(false);
          return;
        }
      } catch (err: unknown) {
        const error = err as Error;
        clearTimeout(timeoutId);
        setIsStartingSession(false);

        if (error.name === 'AbortError') {
          setSessionStartError(t('errors.sessionStartTimeout'));
        } else {
          setSessionStartError(t('errors.sessionStartError', { error: error.message || t('errors.unknownError') }));
        }
        setTimeout(() => setSessionStartError(null), 8000);
        return;
      }
      // Note: We don't reset isStartingSession here to keep the button disabled
      // until submitSymbolAnswer starts (which sets isLoading=true)
    }

    if (!sessionId) {
      setIsStartingSession(false);
      return;
    }

    try {
      const enriched_gloss = glossSymbolUtterance(symbolUtterance);
      const raw_gloss = symbolUtterance.map(s => s.label).join(' ');
      await submitSymbolAnswer(sessionId, symbolUtterance, enriched_gloss, raw_gloss);
      setSymbolUtterance([]);
    } finally {
      setIsStartingSession(false);
    }
  };

  // Symbol fetching for symbol-first view
  const fetchSymbols = useCallback(async () => {
    setSymbolLoading(true);
    try {
      // Fetch all symbols to allow client-side filtering
      const res = await api.get('/boards/symbols', {
        params: {
          limit: 1000,
          language: currentLang
        }
      });
      setSymbolItems(dedupeSymbolItems(res.data || []));
    } catch {
      setSymbolItems([]);
    } finally {
      setSymbolLoading(false);
    }
  }, [currentLang]);

  useEffect(() => {
    if (symbolView) {
      fetchSymbols();
      // Auto-collapse boards when symbol view opens to save space
      setIsBoardsOpen(false);
    }
  }, [symbolView, fetchSymbols]);

  const filteredSymbols = useMemo(() => {
    let items = symbolItems;

    // Search filter
    if (symbolSearch) {
      const q = symbolSearch.toLowerCase();
      items = items.filter(s =>
        s.label.toLowerCase().includes(q) ||
        (s.keywords && s.keywords.toLowerCase().includes(q))
      );
    }

    // Category filter
    if (selectedCategory !== 'all') {
      if (selectedCategory === 'food') {
        items = items.filter(s => s.category === 'food' || s.category === 'drinks');
      } else {
        items = items.filter(s => s.category === selectedCategory);
      }
    }

    return items;
  }, [symbolItems, symbolSearch, selectedCategory]);

  // Core words for sidebar
  const coreWords = useMemo(() => {
    const CORE_WORDS_MAP: Record<string, string[]> = {
      en: ['I', 'you', 'want', 'go', 'stop', 'help', 'yes', 'no', 'more', 'finished', 'like', 'eat', 'drink'],
      es: ['yo', 'tú', 'quiero', 'ir', 'parar', 'ayuda', 'sí', 'no', 'más', 'terminado', 'me gusta', 'comer', 'beber'],
    };
    const priorityWords = CORE_WORDS_MAP[currentLang] || CORE_WORDS_MAP['en'];

    const inPriority = symbolItems.filter(s => priorityWords.includes(s.label));
    const byLabel = new Map<string, SymbolItem>();
    for (const sym of inPriority) {
      const key = sym.label.trim().toLowerCase();
      const existing = byLabel.get(key);
      if (!existing || (!existing.image_path && sym.image_path)) byLabel.set(key, sym);
    }

    return Array.from(byLabel.values()).sort((a, b) => {
      const aP = priorityWords.indexOf(a.label);
      const bP = priorityWords.indexOf(b.label);
      return aP - bP;
    });
  }, [symbolItems, currentLang]);

  const CATEGORIES = [
    { id: 'all', label: t('categories.all') },
    { id: 'core', label: t('categories.core') },
    { id: 'people', label: t('categories.people') },
    { id: 'action', label: t('categories.action') },
    { id: 'feeling', label: t('categories.feeling') },
    { id: 'food', label: t('categories.food') },
    { id: 'object', label: t('categories.object') },
    { id: 'place', label: t('categories.place') },
    { id: 'social', label: t('categories.social') },
    { id: 'ARASAAC', label: t('categories.ARASAAC') },
  ];

  const handleStartActivity = async (topic: string, purpose: string, boardId?: number) => {
    if (!user) return;

    // Fix #2: Add loading state and timeout for manual session start
    setIsStartingSession(true);
    setSessionStartError(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, 30000); // 30 second timeout

    try {
      await startSession({
        topic,
        purpose,
        difficulty: 'basic',
        board_id: boardId
      }, user.id);
      clearTimeout(timeoutId);
    } catch (err: unknown) {
      clearTimeout(timeoutId);
      const error = err as Error;

      if (error.name === 'AbortError') {
        setSessionStartError(t('errors.sessionStartTimeout'));
      } else {
        setSessionStartError(t('errors.sessionStartError', { error: error.message || t('errors.unknownError') }));
      }
      setTimeout(() => setSessionStartError(null), 8000);
    } finally {
      setIsStartingSession(false);
    }
  };



  const handleLoadSession = async (sessionId: number) => {
    await loadSession(sessionId);
    setShowHistory(false);
  };

  const handleNewConversation = async () => {
    if (!user) return;

    // Fix #2: Add loading state and timeout
    setIsStartingSession(true);
    setSessionStartError(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, 30000);

    try {
      await startSession({
        topic: 'general conversation',
        difficulty: 'basic',
        purpose: 'practice'
      }, user.id);
      clearTimeout(timeoutId);
      setShowHistory(false);
    } catch (err: unknown) {
      clearTimeout(timeoutId);
      const error = err as Error;

      if (error.name === 'AbortError') {
        setSessionStartError(t('errors.sessionStartTimeout'));
      } else {
        setSessionStartError(t('errors.sessionStartError', { error: error.message || t('errors.unknownError') }));
      }
      setTimeout(() => setSessionStartError(null), 8000);
    } finally {
      setIsStartingSession(false);
    }
  };

  const { providerInUse, providerHistory } = useLearningStore();
  const [providerNotice, setProviderNotice] = useState<string | null>(null);
  const lastLengthRef = useRef(0);

  useEffect(() => {
    const currentLength = providerHistory.length;
    if (currentLength > lastLengthRef.current && currentLength > 0) {
      const last = providerHistory[currentLength - 1];
      lastLengthRef.current = currentLength;
      // Use microtask to avoid synchronous setState in effect body
      Promise.resolve().then(() => {
        setProviderNotice(`Switched to ${last.provider === 'openrouter' ? 'OpenRouter' : 'Ollama'}`);
      });
      const t = setTimeout(() => setProviderNotice(null), 3000);
      return () => clearTimeout(t);
    }
  }, [providerHistory]);

  // Auto-speak assistant responses
  useEffect(() => {
    if (!voiceEnabled || messages.length === 0) return;

    const lastMsg = messages[messages.length - 1];
    if (lastMsg.role === 'assistant') {
      const content = lastMsg.content;

      // Avoid re-speaking the same message
      if (content === lastSpokenMessageRef.current) return;
      lastSpokenMessageRef.current = content;

      // Ensure we only speak the clean text, even if admin mode shows reasoning
      const textToSpeak = stripReasoning(content);

      if (textToSpeak) {
        tts.enqueue(textToSpeak, { rate: 0.9 });
      }
    }
  }, [messages, voiceEnabled]);

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col">
      <div className="mb-6 flex justify-between items-start">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center">
              <Sparkles className="w-6 h-6 text-indigo-600 dark:text-indigo-400 mr-2" />
              {t('title')}
            </h1>
            <p className="text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors text-sm font-medium"
            >
              {showHistory ? t('hideHistory', 'Hide History') : t('showHistory')}
            </button>
            <button
              onClick={() => setSymbolView(!symbolView)}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${symbolView ? 'bg-indigo-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}`}
              title="Toggle symbol-first view"
            >
              <GridIcon className="w-4 h-4 inline-block mr-2" />
              {symbolView ? t('textChat') : t('symbolFirst')}
            </button>
            <div className="flex items-center gap-2 border-l border-gray-200 dark:border-gray-600 pl-3 ml-1">
              <label htmlFor="learning-mode" className="text-xs font-medium text-gray-500 dark:text-gray-400">Mode:</label>
              <select
                id="learning-mode"
                name="learning_mode"
                value={selectedModeKey}
                onChange={(e) => setSelectedModeKey(e.target.value)}
                className="px-2 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-700 border-none text-sm text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500"
              >
                {availableModes.map(mode => (
                  <option key={mode.key} value={mode.key}>{mode.name}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {providerInUse && (
            <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border ${providerInUse === 'openrouter'
              ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800'
              : 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800'
              }`} title="Current AI provider">
              {providerInUse === 'openrouter' ? (
                <Cloud className="w-4 h-4" />
              ) : (
                <Cpu className="w-4 h-4" />
              )}
              <span>AI: {providerInUse === 'openrouter' ? 'OpenRouter' : 'Ollama'}</span>
            </span>
          )}
          {providerNotice && (
            <div className="px-3 py-1 rounded-md text-xs bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800" role="status">
              {providerNotice}
            </div>
          )}
          <button
            onClick={() => setVoiceEnabled(!voiceEnabled)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${voiceEnabled
              ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 hover:bg-indigo-200 dark:hover:bg-indigo-900/50'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
            title={voiceEnabled ? 'Disable voice input' : 'Enable voice input'}
          >
            {voiceEnabled ? (
              <>
                <Volume2 className="w-5 h-5" />
                <span className="text-sm font-medium">{t('voiceOn')}</span>
              </>
            ) : (
              <>
                <VolumeX className="w-5 h-5" />
                <span className="text-sm font-medium">Voice Off</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className="flex-1 flex gap-4 overflow-hidden">
        {showHistory && (
          <div className="w-80 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('conversationHistory')}</h3>
              <button
                onClick={handleNewConversation}
                className="mt-2 w-full px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
              >
                {t('newConversation')}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2">
              {isLoadingHistory ? (
                <div className="flex justify-center p-4">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600"></div>
                </div>
              ) : sessionHistory.length === 0 ? (
                <div className="text-center text-gray-500 dark:text-gray-400 text-sm p-4">{t('noPrevious')}</div>
              ) : (
                <div className="space-y-2">
                  {sessionHistory.map((session) => (
                    <button
                      key={session.id}
                      onClick={() => handleLoadSession(session.id)}
                      className={`w-full text-left p-3 rounded-lg border transition-colors ${currentSession?.session_id === session.id
                        ? 'bg-indigo-50 dark:bg-indigo-900/30 border-indigo-300 dark:border-indigo-700'
                        : 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                        }`}
                    >
                      <div className="font-medium text-gray-900 dark:text-gray-100 text-sm truncate">
                        {session.topic}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {new Date(session.created_at).toLocaleDateString()}
                      </div>
                      {session.comprehension_score !== undefined && (
                        <div className="text-xs text-indigo-600 dark:text-indigo-400 mt-1">
                          {t('score')} {Math.round(session.comprehension_score * 100)}%
                        </div>
                      )}
                      <div className={`text-xs mt-1 ${session.status === 'completed' ? 'text-green-600 dark:text-green-400' : 'text-orange-600 dark:text-orange-400'
                        }`}>
                        {session.status === 'completed' ? t('completed') : t('inProgress')}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="flex-1 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-gray-900/50">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <div className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Learning Companion</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Practice questions, explanations, and conversational support
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
              {isAdmin && (
                <label className="flex items-center gap-1 cursor-pointer select-none">
                  <input
                    id="show-admin-reasoning"
                    name="show_admin_reasoning"
                    type="checkbox"
                    className="mr-1"
                    checked={showAdminReasoning}
                    onChange={(e) => setShowAdminReasoning(e.target.checked)}
                  />
                  <span>Show thinking</span>
                </label>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Fix #1 & #2: Loading indicator during session start */}
            {isStartingSession && (
              <div className="flex justify-center items-center p-6 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg border border-indigo-200 dark:border-indigo-800">
                <div className="text-center">
                  <div className="inline-flex items-center justify-center mb-3">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                  </div>
                  <p className="text-indigo-700 dark:text-indigo-300 font-medium">{t('startingSession')}</p>
                  <p className="text-indigo-600 dark:text-indigo-400 text-sm mt-1">{t('mayTake')}</p>
                </div>
              </div>
            )}

            {/* Fix #3: Error message display */}
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
                  onClick={() => user && handleNewConversation()}
                  aria-label="Start Session"
                  className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  disabled={isStartingSession}
                >
                  {isStartingSession ? t('startingSession') : t('startSession')}
                </button>
              </div>
            )}

            {messages.map((message, index) => {
              // Safely check content
              const content = message.content || '';
              const symbolData = message.symbolImages;
              const isSymbolMessage = Boolean(symbolData && symbolData.length > 0);
              const isEditing = editingMessageIndex === index;

              // Show editor if this message is being edited
              if (isEditing && isSymbolMessage && symbolData && symbolData.length > 0) {
                return (
                  <div key={index} className="flex justify-end">
                    <div className="max-w-[80%] w-full">
                      <SymbolMessageEditor
                        message={{
                          content: message.content,
                          symbolImages: symbolData as { id: number; label: string; image_path?: string; category?: string }[]
                        }}
                        onUpdate={async (newSymbols) => {
                          if (currentSession && newSymbols.length > 0) {
                            const enriched_gloss = glossSymbolUtterance(newSymbols);
                            const raw_gloss = newSymbols.map(s => s.label).join(' ');
                            await submitSymbolAnswer(currentSession.session_id, newSymbols, enriched_gloss, raw_gloss);
                          }
                          setEditingMessageIndex(null);
                        }}
                        onCancel={() => setEditingMessageIndex(null)}
                      />
                    </div>
                  </div>
                );
              }

              return (
                <div
                  key={index}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} group relative`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${message.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-br-none'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-bl-none'
                      }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center opacity-75 text-xs">
                        {message.role === 'assistant' && <Bot className="w-3 h-3 mr-1" />}
                        {isSymbolMessage && <GridIcon className="w-3 h-3 mr-1" />}
                        <span className="capitalize">{message.role}</span>
                      </div>
                      {/* Edit button for user symbol messages */}
                      {message.role === 'user' && isSymbolMessage && symbolData && symbolData.length > 0 && (
                        <button
                          onClick={() => setEditingMessageIndex(index)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-white/20 rounded"
                          title="Edit symbols"
                          aria-label="Edit symbol message"
                        >
                          <Edit className="w-3 h-3" />
                        </button>
                      )}
                    </div>

                    {/* Symbol images row */}
                    {symbolData && symbolData.length > 0 && (
                      <div className="flex gap-1 mb-2 flex-wrap">
                        {symbolData.map((sym: { label: string; image_path?: string; category?: string }, idx: number) => (
                          <div
                            key={idx}
                            className="w-8 h-8 rounded bg-white/10 overflow-hidden border border-white/20"
                            title={sym.label}
                          >
                            {sym.image_path ? (
                              <img
                                src={assetUrl(sym.image_path)}
                                alt={sym.label}
                                className="w-full h-full object-contain"
                              />
                            ) : (
                              <GridIcon className="w-4 h-4 m-auto mt-2 text-white/40" />
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    <p className="whitespace-pre-wrap">{content}</p>
                  </div>
                </div>
              );
            })}
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

          <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
            <div className="mb-3">
              <Smartbar
                currentSentence={inputToSymbols(input)}
                onSelectSymbol={(symbol) => {
                  const label = symbol.custom_text || symbol.symbol.label;
                  setInput(prev => {
                    const trailingSpace = prev.endsWith(' ') || prev === '' ? '' : ' ';
                    return prev + trailingSpace + label + ' ';
                  });
                }}
                boardId={currentSession?.board_id ?? null}
              />
            </div>
            <form onSubmit={handleSend} className="flex gap-2">
              <input
                id="learning-text-input"
                name="learning_text_input"
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
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
                  )
                  }
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
        </div>

        {/* Saved topics / quick start panel */}
        <BoardsAndTopicsSidebar
          isOpen={isBoardsOpen}
          onToggle={() => setIsBoardsOpen(!isBoardsOpen)}
          onStartActivity={handleStartActivity}
          isStartingSession={isStartingSession}
        />

        {/* Symbol-first view */}
        {symbolView && (
          <div className="w-[450px] bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('symbolFirst')}</h3>

              {/* Utterance Builder */}
              {symbolUtterance.length > 0 && (
                <div className="mb-2 bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">{t('utteranceBuilder')}</div>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {symbolUtterance.map((s, idx) => (
                      <span key={`${s.id}-${idx}`} className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${getCategoryColor(s.category)}`}>
                        {s.label}
                        <button
                          type="button"
                          onClick={() => removeSymbolAt(idx)}
                          className="hover:opacity-70 ml-1"
                          aria-label="Remove symbol"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const text = glossSymbolUtterance(symbolUtterance);
                        if (text && window.speechSynthesis) {
                          const utterance = new SpeechSynthesisUtterance(text);
                          utterance.lang = 'en-US';
                          utterance.rate = 0.9; // Slightly slower for clarity
                          window.speechSynthesis.speak(utterance);
                        }
                      }}
                      className="px-3 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg text-xs hover:bg-gray-300 dark:hover:bg-gray-600 flex items-center gap-1"
                      disabled={symbolUtterance.length === 0}
                      title={t('speakOnly')}
                    >
                      <Volume2 className="w-4 h-4" />
                      {t('speakOnly')}
                    </button>

                    <button
                      type="button"
                      onClick={sendSymbolUtterance}
                      className="px-3 py-2 bg-indigo-600 text-white rounded-lg text-xs hover:bg-indigo-700 disabled:opacity-50"
                      disabled={isLoading || symbolUtterance.length === 0 || isStartingSession}
                    >
                      {isStartingSession ? t('startingSession') : t('sendSymbols')}
                    </button>

                    <button
                      type="button"
                      onClick={clearSymbolUtterance}
                      className="px-3 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg text-xs hover:bg-gray-300 dark:hover:bg-gray-600"
                      disabled={isLoading || isStartingSession}
                    >
                      {t('clear')}
                    </button>
                  </div>
                </div>
              )}

              <div className="mt-3 flex gap-2">
                <div className="relative flex-1">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
                  <input
                    id="learning-symbol-search"
                    name="learning_symbol_search"
                    value={symbolSearch}
                    onChange={(e) => setSymbolSearch(e.target.value)}
                    placeholder={t('search')}
                    className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                  />
                </div>
              </div>

              {/* Categories */}
              <div className="mt-3 flex gap-1 overflow-x-auto pb-2 scrollbar-hide">
                {CATEGORIES.map(cat => (
                  <button
                    key={cat.id}
                    onClick={() => setSelectedCategory(cat.id)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${selectedCategory === cat.id
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                      }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 flex overflow-hidden">
              {/* Core Words Sidebar */}
              <div className="w-24 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 overflow-y-auto p-2 space-y-2">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-2 text-center">{t('categories.core')}</div>
                {coreWords.map(sym => (
                  <button
                    key={`core-${sym.id}`}
                    onClick={() => {
                      setSymbolUtterance(prev => [...prev, { id: sym.id, label: sym.label, category: sym.category, image_path: sym.image_path }]);
                    }}
                    className={`w-full p-2 rounded-lg border text-center text-xs font-medium hover:brightness-95 transition-all ${getCategoryColor(sym.category)}`}
                  >
                    {sym.label}
                  </button>
                ))}
              </div>

              {/* Main Grid */}
              <div className="flex-1 overflow-y-auto p-3 grid grid-cols-3 gap-2 content-start">
                {symbolLoading ? (
                  <div className="col-span-3 text-center text-gray-500 py-8">{t('loading')}</div>
                ) : filteredSymbols.length === 0 ? (
                  <div className="col-span-3 text-center text-gray-500 py-8">{t('noSymbols')}</div>
                ) : (
                  filteredSymbols.map((sym) => (
                    <button
                      key={sym.id}
                      onClick={() => {
                        setSymbolUtterance(prev => [...prev, { id: sym.id, label: sym.label, category: sym.category, image_path: sym.image_path }]);
                      }}
                      className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 hover:border-indigo-500 text-center flex flex-col items-center h-24 justify-center"
                      title={sym.label}
                    >
                      {sym.image_path ? (
                        <img src={assetUrl(sym.image_path)} alt={sym.label} className="w-10 h-10 object-contain mb-1" />
                      ) : (
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-1 ${getCategoryColor(sym.category)} bg-opacity-20`}>
                          <span className="text-xs font-bold">{sym.label.substring(0, 2).toUpperCase()}</span>
                        </div>
                      )}
                      <span className="text-xs font-medium text-gray-900 dark:text-gray-100 leading-tight line-clamp-2">{sym.label}</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
