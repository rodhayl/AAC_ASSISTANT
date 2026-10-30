import { create } from 'zustand';
import api from '../lib/api';
import { useAuthStore } from './authStore';
import type {
  LearningSessionStart,
  LearningSessionResponse,
  QuestionResponse,
  AnswerResponse
} from '../types';

interface WithProvider {
  provider_used?: 'ollama' | 'openrouter';
}

interface SessionHistoryItem {
  id: number;
  topic: string;
  purpose: string;
  status: string;
  created_at: string;
  completed_at?: string;
  comprehension_score?: number;
}

interface LearningState {
  currentSession: LearningSessionResponse | null;
  currentQuestion: QuestionResponse | null;
  lastAnswer: AnswerResponse | null;
  isLoading: boolean;
  error: string | null;
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    symbolImages?: Array<{ label: string; image_path?: string; category?: string }>;
  }>;
  providerInUse?: 'ollama' | 'openrouter';
  providerHistory: Array<{ provider: 'ollama' | 'openrouter'; at: number }>;
  sessionHistory: SessionHistoryItem[];
  isLoadingHistory: boolean;

   // Admin-only toggle: whether to show full reasoning / <think> content
   showAdminReasoning: boolean;
   setShowAdminReasoning: (value: boolean) => void;

  startSession: (data: LearningSessionStart, userId: number) => Promise<void>;
  askQuestion: (sessionId: number, difficulty?: string) => Promise<void>;
  submitAnswer: (sessionId: number, answer: string) => Promise<void>;
  submitVoiceAnswer: (sessionId: number, audioBlob: Blob) => Promise<void>;
  submitSymbolAnswer: (sessionId: number, symbols: Array<{ id: number; label: string; category?: string; image_path?: string }>, enriched_gloss?: string, raw_gloss?: string) => Promise<void>;
  endSession: (sessionId: number) => Promise<void>;
  fetchSessionHistory: (userId: number) => Promise<void>;
  loadSession: (sessionId: number) => Promise<void>;
  clearError: () => void;
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

export const useLearningStore = create<LearningState>((set, get) => ({
  currentSession: null,
  currentQuestion: null,
  lastAnswer: null,
  isLoading: false,
  error: null,
  messages: [],
  providerInUse: undefined,
  providerHistory: [],
  sessionHistory: [],
  isLoadingHistory: false,

   showAdminReasoning: false,
   setShowAdminReasoning: (value: boolean) => set({ showAdminReasoning: value }),

  startSession: async (data, userId) => {
    set({ isLoading: true, error: null, messages: [] });
    try {
      const response = await api.post('/learning/start', data, {
        params: { user_id: userId }
      });

      const session = response.data;

      if (session.success) {
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
          const prev = get().providerInUse
          set({ providerInUse: provider, providerHistory: prev && prev !== provider ? [...get().providerHistory, { provider, at: Date.now() }] : get().providerHistory })
        }
      } else {
        console.error('[startSession] Session failed:', session.error);
        set({ error: session.error || 'Failed to start session', isLoading: false });
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to start session';
        }
        return 'Failed to start session';
      })();
      console.error('[startSession] Error:', error);
      set({ error: detail, isLoading: false });
    }
  },

  askQuestion: async (sessionId, difficulty) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.post(`/learning/${sessionId}/ask`, null, {
        params: { difficulty }
      });
      
      const question = response.data;
      if (question.success) {
        const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
        const showReasoning = Boolean(isAdmin && get().showAdminReasoning);
        const prev = get().messages;
        set({
          currentQuestion: question,
          messages: [...prev, { role: 'assistant' as const, content: formatAssistantContent(question.question_text || 'Question ready', showReasoning) }],
          isLoading: false
        });
        const questionWithProvider = question as QuestionResponse & WithProvider
        if (questionWithProvider.provider_used) {
          const provider = questionWithProvider.provider_used
          const prev = get().providerInUse
          set({ providerInUse: provider, providerHistory: prev && prev !== provider ? [...get().providerHistory, { provider, at: Date.now() }] : get().providerHistory })
        }
      } else {
        set({ error: question.error || 'Failed to get question', isLoading: false });
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to get question';
        }
        return 'Failed to get question';
      })();
      set({ error: detail, isLoading: false });
    }
  },

  submitAnswer: async (sessionId, answer) => {
    set({ isLoading: true, error: null });
    // Add user message immediately for UI responsiveness
    set((state) => ({
      messages: [...state.messages, { role: 'user' as const, content: answer }]
    }));

    try {
      const response = await api.post(`/learning/${sessionId}/answer`, {
        answer: answer,
        is_voice: false
      });
      
      const result = response.data;
      if (result.success) {
        const prev = get().messages;
        // Prefer final answer; hide chain-of-thought unless admin
        const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
        const showReasoning = Boolean(isAdmin && get().showAdminReasoning);
        const reply = buildAssistantReply(result, showReasoning);
        set({
          lastAnswer: result,
          messages: [...prev, { role: 'assistant' as const, content: reply }],
          isLoading: false
        });
        const { user } = useAuthStore.getState()
        if (user) {
          try { await api.post(`/achievements/user/${user.id}/check`) } catch { /* achievement check optional */ }
        }
        const resultWithProvider = result as AnswerResponse & WithProvider
        if (resultWithProvider.provider_used) {
          const provider = resultWithProvider.provider_used
          const prev = get().providerInUse
          set({ providerInUse: provider, providerHistory: prev && prev !== provider ? [...get().providerHistory, { provider, at: Date.now() }] : get().providerHistory })
        }
      } else {
        set({ error: result.error || 'Failed to submit answer', isLoading: false });
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string; error?: string; message?: string } } };
          return r.response?.data?.detail || r.response?.data?.error || r.response?.data?.message || 'Failed to submit answer';
        }
        return 'Failed to submit answer';
      })();
      set({ error: detail, isLoading: false });
    }
  },

  submitVoiceAnswer: async (sessionId, audioBlob) => {
    set({ isLoading: true, error: null });
    
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.wav');

    try {
      const response = await api.post(`/learning/${sessionId}/answer/voice`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      const result = response.data;
      if (result.success) {
        const prev = get().messages;
        const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
        const showReasoning = Boolean(isAdmin && get().showAdminReasoning);
        const reply = buildAssistantReply(result, showReasoning);
        set({
          lastAnswer: result,
          messages: [
            ...prev,
            { role: 'user' as const, content: `[voice] ${result.transcription || 'Audio message'}` },
            { role: 'assistant' as const, content: reply }
          ],
          isLoading: false
        });
        const { user } = useAuthStore.getState()
        if (user) {
          try { await api.post(`/achievements/user/${user.id}/check`) } catch { /* achievement check optional */ }
        }
        const resultWithProvider = result as AnswerResponse & WithProvider
        if (resultWithProvider.provider_used) {
          const provider = resultWithProvider.provider_used
          const prev = get().providerInUse
          set({ providerInUse: provider, providerHistory: prev && prev !== provider ? [...get().providerHistory, { provider, at: Date.now() }] : get().providerHistory })
        }
      } else {
        set({ error: result.error || 'Failed to submit voice answer', isLoading: false });
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string; error?: string; message?: string } } };
          return r.response?.data?.detail || r.response?.data?.error || r.response?.data?.message || 'Failed to submit voice answer';
        }
        return 'Failed to submit voice answer';
      })();
      set({ error: detail, isLoading: false });
    }
  },

  submitSymbolAnswer: async (sessionId, symbols, enriched_gloss, raw_gloss) => {
    set({ isLoading: true, error: null });

    // Build a readable user message for the chat UI using enriched gloss
    const userMessage = enriched_gloss || raw_gloss || symbols.map(s => s.label).join(' ');
    const userContent = userMessage || '[symbols]';

    // Optimistically show user message with symbol images
    set((state) => ({
      messages: [...state.messages, {
        role: 'user' as const,
        content: userContent,
        symbolImages: symbols.map(s => ({
          label: s.label,
          image_path: s.image_path,
          category: s.category
        }))
      }]
    }));

    try {
      const response = await api.post(`/learning/${sessionId}/answer/symbols`, {
        symbols,
        enriched_gloss: enriched_gloss || undefined,
        raw_gloss: raw_gloss || undefined,
        text: userMessage || undefined, // Keep for backwards compatibility
      });

      const result = response.data;
      if (result.success) {
        const prev = get().messages;
        const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
        const showReasoning = Boolean(isAdmin && get().showAdminReasoning);
        const reply = buildAssistantReply(result, showReasoning);
        set({
          lastAnswer: result,
          messages: [
            ...prev,
            { role: 'assistant' as const, content: reply }
          ],
          isLoading: false
        });
        const { user } = useAuthStore.getState();
        if (user) {
          try { await api.post(`/achievements/user/${user.id}/check`) } catch { /* achievement check optional */ }
        }
        const resultWithProvider = result as AnswerResponse & WithProvider;
        if (resultWithProvider.provider_used) {
          const provider = resultWithProvider.provider_used;
          const prev = get().providerInUse;
          set({ providerInUse: provider, providerHistory: prev && prev !== provider ? [...get().providerHistory, { provider, at: Date.now() }] : get().providerHistory });
        }
      } else {
        set({ error: result.error || 'Failed to submit symbol answer', isLoading: false });
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string; error?: string; message?: string } } };
          return r.response?.data?.detail || r.response?.data?.error || r.response?.data?.message || 'Failed to submit symbol answer';
        }
        return 'Failed to submit symbol answer';
      })();
      set({ error: detail, isLoading: false });
    }
  },

  endSession: async (sessionId) => {
    set({ isLoading: true, error: null });
    try {
      await api.post(`/learning/${sessionId}/end`);
      set({ currentSession: null, currentQuestion: null, lastAnswer: null, isLoading: false });
      const { user } = useAuthStore.getState()
      if (user) {
        try { await api.post(`/achievements/user/${user.id}/check`) } catch { /* achievement check optional */ }
        get().fetchSessionHistory(user.id);
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to end session';
        }
        return 'Failed to end session';
      })();
      set({ error: detail, isLoading: false });
    }
  },

  fetchSessionHistory: async (userId) => {
    set({ isLoadingHistory: true });
    try {
      const response = await api.get(`/learning/history/${userId}`, {
        params: { limit: 50 }
      });
      set({ sessionHistory: response.data.sessions || [], isLoadingHistory: false });
    } catch (error) {
      console.error('Failed to fetch session history:', error);
      set({ isLoadingHistory: false });
    }
  },

  loadSession: async (sessionId) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.get(`/learning/${sessionId}/progress`);
      const sessionData = response.data;
      const isAdmin = useAuthStore.getState().user?.user_type === 'admin';
      const showReasoning = Boolean(isAdmin && get().showAdminReasoning);

      // Reconstruct messages from conversation_history
      const messages: Array<{ role: 'user' | 'assistant', content: string }> = [];

      if (sessionData.conversation_history && Array.isArray(sessionData.conversation_history)) {
        for (const entry of sessionData.conversation_history) {
          if (entry.type === 'question' && entry.data?.question) {
            messages.push({ role: 'assistant' as const, content: formatAssistantContent(entry.data.question, showReasoning) });
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
              messages.push({ role: 'assistant' as const, content: formatAssistantContent(entry.feedback, showReasoning) });
            }
          }
        }
      }

      // console.log('[loadSession] Reconstructed messages:', messages);

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
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to load session';
        }
        return 'Failed to load session';
      })();
      console.error('[loadSession] Error:', error);
      set({ error: detail, isLoading: false });
    }
  },

  clearError: () => set({ error: null })
}));
