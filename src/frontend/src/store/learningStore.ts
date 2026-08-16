import { create } from 'zustand';
import api, { extractError } from '../lib/api';
import { useAuthStore } from './authStore';
import type {
  LearningSessionStart,
  LearningSessionResponse,
  QuestionResponse,
  AnswerResponse
} from '../types';

interface WithProvider {
  provider_used?: 'ollama' | 'openrouter' | 'lmstudio';
}

export interface SessionHistoryItem {
  id: number;
  topic: string;
  purpose: string;
  status: string;
  created_at: string;
  completed_at?: string;
  comprehension_score?: number;
}

// In-session progress shown in the chat header: live comprehension score,
// answered/correct counters and the current adaptive difficulty.
export type DifficultyOverride = 'adaptive' | 'basic' | 'intermediate' | 'advanced';

export interface LearningProgress {
  comprehensionScore?: number;
  questionsAnswered?: number;
  correctAnswers?: number;
  difficulty?: string;
}

// Correct-answer reveal state for the question card: which choice was picked
// and whether it was right (null = no verdict, e.g. a voice answer).
export interface RevealedAnswer {
  choice: string;
  isCorrect: boolean | null;
}

// Returned by the end-session endpoint and shown in the summary modal.
export interface SessionSummary {
  success?: boolean;
  session_id?: number;
  summary?: string;
  comprehension_score?: number;
  questions_answered?: number;
  correct_answers?: number;
  provider_used?: string;
  source?: 'llm' | 'fallback';
  statistics?: {
    questions_asked?: number;
    questions_answered?: number;
    correct_answers?: number;
    comprehension_score?: number;
  };
}

interface LearningState {
  currentSession: LearningSessionResponse | null;
  currentQuestion: QuestionResponse | null;
  lastAnswer: AnswerResponse | null;
  revealedAnswer: RevealedAnswer | null;
  progressStats: LearningProgress | null;
  lastSessionSummary: SessionSummary | null;
  isLoading: boolean;
  error: string | null;
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    symbolImages?: Array<{ label: string; image_path?: string; category?: string }>;
    source?: 'llm' | 'fallback';
  }>;
  providerInUse?: 'ollama' | 'openrouter' | 'lmstudio';
  providerHistory: Array<{ provider: 'ollama' | 'openrouter' | 'lmstudio'; at: number }>;
  sessionHistory: SessionHistoryItem[];
  isLoadingHistory: boolean;

   // Admin-only toggle: whether to show full reasoning / <think> content
   showAdminReasoning: boolean;
   setShowAdminReasoning: (value: boolean) => void;

  // Pause the adaptive question flow while symbol-first view is active.
  autoAskEnabled: boolean;
  setAutoAskEnabled: (enabled: boolean) => void;
  difficultyOverride: DifficultyOverride;
  setDifficultyOverride: (difficulty: DifficultyOverride) => void;

  startSession: (data: LearningSessionStart, userId: number) => Promise<void>;
  askQuestion: (sessionId: number, difficulty?: string) => Promise<void>;
  askNextQuestion: (difficulty?: string) => Promise<void>;
  submitAnswer: (sessionId: number, answer: string) => Promise<void>;
  submitVoiceAnswer: (sessionId: number, audioBlob: Blob) => Promise<void>;
  submitSymbolAnswer: (sessionId: number, symbols: Array<{ id: number; label: string; category?: string; image_path?: string }>, enriched_gloss?: string, raw_gloss?: string) => Promise<void>;
  endSession: (sessionId: number) => Promise<void>;
  fetchSessionHistory: (userId: number) => Promise<void>;
  loadSession: (sessionId: number) => Promise<void>;
  clearError: () => void;
  clearSessionSummary: () => void;
  resetSession: () => void;
}

// Strip model reasoning from text - lightweight fallback for legacy data
// With backend JSON mode, this should rarely be needed
export function stripReasoning(text: string): string {
  if (!text) return '';
  let cleaned = text;

  // Remove explicit reasoning blocks
  cleaned = cleaned.replace(/```(?:thinking|reasoning)[\s\S]*?```/gi, '');
  cleaned = cleaned.replace(/<think>[\s\S]*?<\/think>/gi, '');
  cleaned = cleaned.replace(/<\/?think>/gi, '');

  // If there's an explicit answer marker, extract that
  const markers = ['final answer:', 'final response:', 'answer:', 'response:'];
  for (const marker of markers) {
    const idx = cleaned.toLowerCase().lastIndexOf(marker);
    if (idx !== -1) {
      cleaned = cleaned.slice(idx + marker.length).trim();
      break;
    }
  }

  return cleaned.trim();
}

function buildAssistantReply(
  payload: Partial<AnswerResponse> & Partial<QuestionResponse>,
  includeReasoning: boolean
): string {
  const primaryRaw =
    payload.assistant_reply ||
    payload.feedback_message ||
    payload.encouraging_feedback ||
    payload.message ||
    '';

  if (includeReasoning) {
    const base = primaryRaw || 'Answer received';
    if (payload.full_thinking) {
      return `${base}\n\n[debug] ${payload.full_thinking}`.trim();
    }
    return base;
  }

  const cleaned = stripReasoning(primaryRaw);
  return cleaned || 'Answer received';
}

function formatAssistantContent(content: string | undefined, includeReasoning: boolean): string {
  if (!content) return '';
  return includeReasoning ? content : stripReasoning(content);
}

// How long the correct-answer reveal stays visible after answering before the
// next adaptive question auto-loads. Short enough to keep the quiz moving,
// long enough for the student to see which answer was right.
export const NEXT_QUESTION_REVEAL_DELAY_MS = 1500;

// Single pending auto-ask timer; replaced or cancelled when the student asks
// for a question manually, starts/ends a session, or answers again.
let nextQuestionTimer: ReturnType<typeof setTimeout> | null = null;
let sessionEpoch = 0;
let questionRequestId = 0;
let answerRequestId = 0;
let historyRequestId = 0;
let achievementCheckController: AbortController | null = null;

function isCurrentContextRequest(epoch: number): boolean {
  return epoch === sessionEpoch;
}

function isCurrentOperationRequest(
  epoch: number,
  operationId: number,
  currentOperationId: number,
  sessionId: number,
  get: () => LearningState,
): boolean {
  return (
    epoch === sessionEpoch &&
    operationId === currentOperationId &&
    get().currentSession?.session_id === sessionId
  );
}

function cancelPendingAutoAsk(): void {
  if (nextQuestionTimer !== null) {
    clearTimeout(nextQuestionTimer);
    nextQuestionTimer = null;
  }
}

function scheduleAutoAsk(
  get: () => LearningState,
  epoch: number,
  sessionId: number,
): void {
  cancelPendingAutoAsk();
  nextQuestionTimer = setTimeout(() => {
    nextQuestionTimer = null;
    if (epoch !== sessionEpoch || get().currentSession?.session_id !== sessionId) return;
    void get().askNextQuestion();
  }, NEXT_QUESTION_REVEAL_DELAY_MS);
}

function mergeProgress(current: LearningProgress | null, result: Partial<AnswerResponse>): LearningProgress {
  return {
    ...(current ?? {}),
    comprehensionScore: result.comprehension_score ?? current?.comprehensionScore,
    questionsAnswered: result.questions_answered ?? current?.questionsAnswered,
    correctAnswers: result.correct_answers ?? current?.correctAnswers,
  };
}

function setProviderState(
  set: (state: Partial<LearningState>) => void,
  get: () => LearningState,
  provider: NonNullable<WithProvider['provider_used']>,
): void {
  if (!provider) return;
  const previous = get().providerInUse;
  const providerHistory =
    previous && previous !== provider
      ? [...get().providerHistory, { provider, at: Date.now() }].slice(-10)
      : get().providerHistory;
  set({ providerInUse: provider, providerHistory });
}

/**
 * Achievement refresh is best-effort and independent from the answer result.
 * Keep it out of the answer critical path so a slow achievement query cannot
 * delay the next-question reveal or make the learning UI feel unresponsive.
 */
function cancelAchievementCheck(): void {
  achievementCheckController?.abort();
  achievementCheckController = null;
}

async function triggerAchievementCheck(userId: number): Promise<void> {
  cancelAchievementCheck();
  if (useAuthStore.getState().user?.id !== userId) return;
  const controller = new AbortController();
  achievementCheckController = controller;
  try {
    await api.post(`/achievements/user/${userId}/check`, undefined, {
      signal: controller.signal,
    });
  } catch {
    // Achievement refresh is optional; the learning result is already saved.
  } finally {
    if (achievementCheckController === controller) {
      achievementCheckController = null;
    }
  }
}

export const useLearningStore = create<LearningState>((set, get) => {
  const finishAnswer = (
    requestEpoch: number,
    requestId: number,
    sessionId: number,
    result: AnswerResponse & WithProvider,
    failureMessage: string,
    choice: string,
    userMessage?: string,
    symbolImages?: Array<{ label: string; image_path?: string; category?: string }>,
  ): void => {
    if (!isCurrentOperationRequest(requestEpoch, requestId, answerRequestId, sessionId, get)) return;
    if (!result.success) {
      set({ error: result.error || failureMessage, isLoading: false });
      return;
    }

    const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
    const showReasoning = Boolean(isAdmin && get().showAdminReasoning);
    const reply = buildAssistantReply(result, showReasoning);
    set((state) => ({
      lastAnswer: result,
      revealedAnswer: { choice, isCorrect: result.is_correct ?? null },
      progressStats: mergeProgress(state.progressStats, result),
      messages: [
        ...state.messages,
        ...(userMessage
          ? [{ role: 'user' as const, content: userMessage, ...(symbolImages ? { symbolImages } : {}) }]
          : []),
        { role: 'assistant' as const, content: reply, source: result.source },
      ],
      isLoading: false,
    }));

    scheduleAutoAsk(get, requestEpoch, sessionId);
    const { user } = useAuthStore.getState();
    if (user && requestEpoch === sessionEpoch && get().currentSession?.session_id === sessionId) {
      void triggerAchievementCheck(user.id);
    }
    if (result.provider_used) setProviderState(set, get, result.provider_used);
  };

  return {
  currentSession: null,
  currentQuestion: null,
  lastAnswer: null,
  revealedAnswer: null,
  progressStats: null,
  lastSessionSummary: null,
  isLoading: false,
  error: null,
  messages: [],
  providerInUse: undefined,
  providerHistory: [],
  sessionHistory: [],
  isLoadingHistory: false,
  autoAskEnabled: true,
  setAutoAskEnabled: (enabled: boolean) => set({ autoAskEnabled: enabled }),
  difficultyOverride: 'adaptive',
  setDifficultyOverride: (difficulty: DifficultyOverride) => set({ difficultyOverride: difficulty }),

   showAdminReasoning: false,
   setShowAdminReasoning: (value: boolean) => set({ showAdminReasoning: value }),

  clearSessionSummary: () => set({ lastSessionSummary: null }),

  resetSession: () => {
    sessionEpoch += 1;
    questionRequestId += 1;
    answerRequestId += 1;
    historyRequestId += 1;
    cancelPendingAutoAsk();
    cancelAchievementCheck();
    set({
      currentSession: null,
      currentQuestion: null,
      lastAnswer: null,
      revealedAnswer: null,
      progressStats: null,
      lastSessionSummary: null,
      isLoading: false,
      error: null,
      messages: [],
      providerInUse: undefined,
      providerHistory: [],
      sessionHistory: [],
      isLoadingHistory: false,
    });
  },

  startSession: async (data, userId) => {
    const requestEpoch = ++sessionEpoch;
    cancelPendingAutoAsk();
    cancelAchievementCheck();
    set({
      isLoading: true,
      error: null,
      messages: [],
      revealedAnswer: null,
      progressStats: null,
      lastSessionSummary: null,
    });
    try {
      const response = await api.post('/learning/start', data, {
        params: { user_id: userId }
      });

      const session = response.data;

      if (session.success) {
        if (!isCurrentContextRequest(requestEpoch)) return;
        const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
        const showReasoning = Boolean(isAdmin && get().showAdminReasoning);
        const messages = session.welcome_message
          ? [{ role: 'assistant' as const, content: formatAssistantContent(session.welcome_message, showReasoning) }]
          : [];

        set({
          currentSession: session,
          messages,
          isLoading: false
        });
        const sessionWithProvider = session as LearningSessionResponse & WithProvider
        if (sessionWithProvider.provider_used) {
          const provider = sessionWithProvider.provider_used
          setProviderState(set, get, provider)
        }
      } else {
        if (!isCurrentContextRequest(requestEpoch)) return;
        const detail = session.error || 'Failed to start session';
        console.error('[startSession] Session failed:', detail);
        set({ error: detail, isLoading: false });
        throw new Error(detail);
      }
    } catch (error: unknown) {
      if (!isCurrentContextRequest(requestEpoch)) return;
      const detail = (() => {
        if (error instanceof Error) {
          return error.message;
        }
        return extractError(error, 'Failed to start session');
      })();
      console.error('[startSession] Error:', error);
      set({ error: detail, isLoading: false });
      throw error instanceof Error ? error : new Error(detail);
    }
  },

  askQuestion: async (sessionId, difficulty) => {
    if (get().isLoading || get().currentSession?.session_id !== sessionId) return;
    const requestEpoch = sessionEpoch;
    const requestId = ++questionRequestId;
    cancelPendingAutoAsk();
    set({ isLoading: true, error: null, currentQuestion: null, revealedAnswer: null });
    try {
      const response = await api.post(`/learning/${sessionId}/ask`, null, {
        params: { difficulty }
      });
      
      const question = response.data;
      if (!isCurrentOperationRequest(requestEpoch, requestId, questionRequestId, sessionId, get)) return;
      if (question.success) {
        const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
        const showReasoning = Boolean(isAdmin && get().showAdminReasoning);
        const prev = get().messages;
        set({
          currentQuestion: question,
          progressStats: {
            ...(get().progressStats ?? {}),
            difficulty: question.difficulty ?? get().progressStats?.difficulty,
          },
          messages: [...prev, { role: 'assistant' as const, content: formatAssistantContent(question.question_text || 'Question ready', showReasoning), source: question.source }],
          isLoading: false
        });
        const questionWithProvider = question as QuestionResponse & WithProvider
        if (questionWithProvider.provider_used) {
          const provider = questionWithProvider.provider_used
          setProviderState(set, get, provider)
        }
      } else {
        set({ error: question.error || 'Failed to get question', isLoading: false });
      }
    } catch (error: unknown) {
      if (!isCurrentOperationRequest(requestEpoch, requestId, questionRequestId, sessionId, get)) return;
      const detail = (() => {
        return extractError(error, 'Failed to get question');
      })();
      set({ error: detail, isLoading: false });
    }
  },

  askNextQuestion: async (difficulty?: string) => {
    const { currentSession, isLoading, autoAskEnabled, difficultyOverride } = get();
    if (!currentSession || isLoading || !autoAskEnabled) return;
    const requestedDifficulty =
      difficulty ?? (difficultyOverride === 'adaptive' ? undefined : difficultyOverride);
    await get().askQuestion(currentSession.session_id, requestedDifficulty);
  },

  submitAnswer: async (sessionId, answer) => {
    if (get().isLoading || get().currentSession?.session_id !== sessionId) return;
    const requestEpoch = sessionEpoch;
    const requestId = ++answerRequestId;
    set({ isLoading: true, error: null });
    set((state) => ({
      messages: [...state.messages, { role: 'user' as const, content: answer }],
    }));
    try {
      const response = await api.post(`/learning/${sessionId}/answer`, {
        answer,
        is_voice: false,
      });
      finishAnswer(
        requestEpoch,
        requestId,
        sessionId,
        response.data as AnswerResponse & WithProvider,
        'Failed to submit answer',
        answer,
      );
    } catch (error: unknown) {
      if (!isCurrentOperationRequest(requestEpoch, requestId, answerRequestId, sessionId, get)) return;
      set({ error: extractError(error, 'Failed to submit answer'), isLoading: false });
    }
  },

  submitVoiceAnswer: async (sessionId, audioBlob) => {
    if (get().isLoading || get().currentSession?.session_id !== sessionId) return;
    const requestEpoch = sessionEpoch;
    const requestId = ++answerRequestId;
    set({ isLoading: true, error: null });
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.wav');
    try {
      const response = await api.post(`/learning/${sessionId}/answer/voice`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const result = response.data as AnswerResponse & WithProvider;
      finishAnswer(
        requestEpoch,
        requestId,
        sessionId,
        result,
        'Failed to submit voice answer',
        result.transcription || '[voice]',
        `[voice] ${result.transcription || 'Audio message'}`,
      );
    } catch (error: unknown) {
      if (!isCurrentOperationRequest(requestEpoch, requestId, answerRequestId, sessionId, get)) return;
      set({ error: extractError(error, 'Failed to submit voice answer'), isLoading: false });
    }
  },

  submitSymbolAnswer: async (sessionId, symbols, enriched_gloss, raw_gloss) => {
    if (get().isLoading || get().currentSession?.session_id !== sessionId) return;
    const requestEpoch = sessionEpoch;
    const requestId = ++answerRequestId;
    set({ isLoading: true, error: null });
    const userMessage = enriched_gloss || raw_gloss || symbols.map((s) => s.label).join(' ');
    const userContent = userMessage || '[symbols]';
    const symbolImages = symbols.map((s) => ({ label: s.label, image_path: s.image_path, category: s.category }));
    set((state) => ({
      messages: [...state.messages, { role: 'user' as const, content: userContent, symbolImages }],
    }));
    try {
      const response = await api.post(`/learning/${sessionId}/answer/symbols`, {
        symbols,
        enriched_gloss: enriched_gloss || undefined,
        raw_gloss: raw_gloss || undefined,
        text: userMessage || undefined,
      });
      finishAnswer(
        requestEpoch,
        requestId,
        sessionId,
        response.data as AnswerResponse & WithProvider,
        'Failed to submit symbol answer',
        userContent,
      );
    } catch (error: unknown) {
      if (!isCurrentOperationRequest(requestEpoch, requestId, answerRequestId, sessionId, get)) return;
      set({ error: extractError(error, 'Failed to submit symbol answer'), isLoading: false });
    }
  },

  endSession: async (sessionId) => {
    if (get().currentSession?.session_id !== sessionId) return;
    const requestEpoch = ++sessionEpoch;
    cancelPendingAutoAsk();
    cancelAchievementCheck();
    set({ isLoading: true, error: null });
    try {
      const response = await api.post(`/learning/${sessionId}/end`);
      const summary = response.data;
      if (!isCurrentContextRequest(requestEpoch)) return;
      set({
        currentSession: null,
        currentQuestion: null,
        lastAnswer: null,
        revealedAnswer: null,
        progressStats: null,
        lastSessionSummary: summary ?? null,
        isLoading: false,
      });
      const { user } = useAuthStore.getState()
      if (user && requestEpoch === sessionEpoch) {
        void triggerAchievementCheck(user.id);
        void get().fetchSessionHistory(user.id);
      }
    } catch (error: unknown) {
      if (!isCurrentContextRequest(requestEpoch)) return;
      const detail = (() => {
        return extractError(error, 'Failed to end session');
      })();
      set({ error: detail, isLoading: false });
    }
  },

  fetchSessionHistory: async (userId) => {
    const requestId = ++historyRequestId;
    set({ isLoadingHistory: true });
    try {
      const response = await api.get(`/learning/history/${userId}`, {
        params: { limit: 50 }
      });
      if (requestId !== historyRequestId) return;
      set({ sessionHistory: response.data.sessions || [], isLoadingHistory: false });
    } catch (error) {
      if (requestId !== historyRequestId) return;
      console.error('Failed to fetch session history:', error);
      set({ isLoadingHistory: false });
    }
  },

  loadSession: async (sessionId) => {
    const requestEpoch = ++sessionEpoch;
    cancelPendingAutoAsk();
    cancelAchievementCheck();
    set({
      isLoading: true,
      error: null,
      revealedAnswer: null,
      progressStats: null,
      lastSessionSummary: null,
    });
    try {
      const response = await api.get(`/learning/${sessionId}/progress`);
      const sessionData = response.data;
      if (!isCurrentContextRequest(requestEpoch)) return;
      const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
      const showReasoning = Boolean(isAdmin && get().showAdminReasoning);

      // Reconstruct messages from conversation_history
      const messages: Array<{
        role: 'user' | 'assistant';
        content: string;
        source?: 'llm' | 'fallback';
      }> = [];

      if (sessionData.conversation_history && Array.isArray(sessionData.conversation_history)) {
        for (const entry of sessionData.conversation_history) {
          if (entry.type === 'question' && entry.data?.question) {
            messages.push({
              role: 'assistant' as const,
              content: formatAssistantContent(entry.data.question, showReasoning),
              source: entry.source,
            });
          } else if (entry.type === 'response' && entry.student_answer) {
            const isSymbol = entry.mode === 'symbol';
            const symbolList = Array.isArray(entry.symbols)
              ? entry.symbols.map((s: { label: string }) => s.label).filter(Boolean).join(', ')
              : '';
            const content = isSymbol
              ? `🧩 ${entry.student_answer}${symbolList ? `\n[Symbols: ${symbolList}]` : ''}`
              : entry.student_answer;
            messages.push({ role: 'user' as const, content });
            if (entry.feedback) {
              messages.push({
                role: 'assistant' as const,
                content: formatAssistantContent(entry.feedback, showReasoning),
                source: entry.source,
              });
            }
          }
        }
      }


      set({
        currentSession: {
          session_id: sessionData.id,
          success: true,
          welcome_message: messages[0]?.content || ''
        },
        messages,
        isLoading: false
      });
    } catch (error: unknown) {
      if (!isCurrentContextRequest(requestEpoch)) return;
      const detail = (() => {
        return extractError(error, 'Failed to load session');
      })();
      console.error('[loadSession] Error:', error);
      set({ error: detail, isLoading: false });
    }
  },

  clearError: () => set({ error: null })
  };
});

if (typeof window !== 'undefined') {
  const resetForAuthContextChange = () => {
    useLearningStore.getState().resetSession();
  };
  window.addEventListener('aac:auth-logout', resetForAuthContextChange);
  window.addEventListener('aac:auth-context-changed', resetForAuthContextChange);
}
