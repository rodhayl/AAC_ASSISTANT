import { create } from 'zustand';
import api, { extractError } from '../lib/api';
import i18n from '../i18n/index';

export type AiProviderId = 'ollama' | 'openrouter' | 'lmstudio' | 'groq';

export interface AISettings {
  provider: AiProviderId;
  ollama_model: string;
  openrouter_model: string;
  lmstudio_model: string;
  groq_model: string;
  openrouter_api_key?: string;
  groq_api_key?: string;
  ollama_base_url: string;
  lmstudio_base_url: string;
  // Global LLM behavior controls
  max_tokens?: number;
  temperature?: number;
  // Daily cap on auto-generated pictograms (0 disables auto-generation).
  autogen_daily_cap?: number;
  can_edit: boolean;
}

export interface OllamaModel {
  name: string;
  size?: number;
  modified_at?: string;
}

export interface OpenRouterModel {
  id: string;
  name: string;
  pricing?: {
    prompt?: string;
    completion?: string;
  };
  context_length?: number;
}

function tSettings(key: string): string {
  return i18n.isInitialized ? i18n.t(key) : key;
}

interface SettingsState {
  aiSettings: AISettings | null;
  ollamaModels: OllamaModel[];
  openRouterModels: OpenRouterModel[];
  lmStudioModels: OpenRouterModel[];
  groqModels: OpenRouterModel[];
  loading: boolean;
  error: string | null;

  // Actions
  fetchAISettings: () => Promise<void>;
  updateAISettings: (settings: Partial<AISettings>) => Promise<void>;
  fetchOllamaModels: () => Promise<void>;
  fetchOpenRouterModels: (apiKey?: string) => Promise<void>;
  fetchLmStudioModels: () => Promise<void>;
  fetchGroqModels: (apiKey?: string) => Promise<void>;
}

let modelRequestSequence = 0;
let settingsRequestSequence = 0;
let updateRequestSequence = 0;

export const useSettingsStore = create<SettingsState>((set, get) => {

  // The four model-fetch actions share one load-and-store shape; only the
  // endpoint, element type, and failure message differ. A newer request wins
  // so an older response cannot replace a list fetched with newer credentials
  // or clear its loading/error state while it is still in flight. The list is
  // typed per endpoint and guarded at runtime: a missing/non-array ``models``
  // payload becomes an empty list (never ``undefined``), so consumers calling
  // ``.find``/``.length`` on the stored list cannot crash on a shape drift.
  // Returns the fetched list (possibly empty) or null when the result is
  // stale (a newer request owns the state) or the request failed (error
  // already stored).
  const fetchModelList = async <T>(
    endpoint: string,
    failureMessage: string,
    headers?: Record<string, string>
  ): Promise<T[] | null> => {
    const requestId = ++modelRequestSequence;
    set({ loading: true, error: null });
    try {
      const response = headers
        ? await api.get<{ models?: T[] }>(endpoint, { headers })
        : await api.get<{ models?: T[] }>(endpoint);
      if (requestId !== modelRequestSequence) return null;
      const models = response.data?.models;
      return Array.isArray(models) ? models : [];
    } catch (error: unknown) {
      if (requestId !== modelRequestSequence) return null;
      const message = extractError(error, failureMessage);
      set({ error: message, loading: false });
      return null;
    }
  };

  return {
    aiSettings: null,
    ollamaModels: [],
    openRouterModels: [],
    lmStudioModels: [],
    groqModels: [],
    loading: false,
    error: null,

    fetchAISettings: async () => {
      const requestId = ++settingsRequestSequence;
      set({ loading: true, error: null });
      try {
        const response = await api.get('/settings/ai');
        if (requestId !== settingsRequestSequence) return;
        set({ aiSettings: response.data, loading: false });
      } catch (error: unknown) {
        if (requestId !== settingsRequestSequence) return;
        const message = extractError(error, tSettings('settings:ai.fetchFailed'));
        set({ error: message, loading: false });
      }
    },

    updateAISettings: async (settings: Partial<AISettings>) => {
      const requestId = ++updateRequestSequence;
      set({ loading: true, error: null });
      try {
        await api.put('/settings/ai', settings);
        await get().fetchAISettings();
      } catch (error: unknown) {
        if (requestId !== updateRequestSequence) return;
        const message = extractError(error, tSettings('settings:ai.updateFailed'));
        set({ error: message, loading: false });
        throw error;
      }
    },

    fetchOllamaModels: async () => {
      const models = await fetchModelList<OllamaModel>(
        '/settings/ai/models/ollama',
        tSettings('settings:ai.fetchOllamaFailed'),
      );
      if (models !== null) set({ ollamaModels: models, loading: false });
    },

    fetchOpenRouterModels: async (apiKey?: string) => {
      const headers = apiKey?.trim()
        ? { 'X-OpenRouter-API-Key': apiKey.trim() }
        : undefined;
      const models = await fetchModelList<OpenRouterModel>(
        '/settings/ai/models/openrouter',
        tSettings('settings:ai.fetchOpenRouterFailed'),
        headers,
      );
      if (models !== null) set({ openRouterModels: models, loading: false });
    },

    fetchLmStudioModels: async () => {
      const models = await fetchModelList<OpenRouterModel>(
        '/settings/ai/models/lmstudio',
        tSettings('settings:ai.fetchLmStudioFailed'),
      );
      if (models !== null) set({ lmStudioModels: models, loading: false });
    },

    fetchGroqModels: async (apiKey?: string) => {
      const headers = apiKey?.trim()
        ? { 'X-Groq-API-Key': apiKey.trim() }
        : undefined;
      const models = await fetchModelList<OpenRouterModel>(
        '/settings/ai/models/groq',
        tSettings('settings:ai.fetchGroqFailed'),
        headers,
      );
      if (models !== null) set({ groqModels: models, loading: false });
    },
  };
});

if (typeof window !== 'undefined') {
  const resetForAuthContextChange = () => {
    settingsRequestSequence += 1;
    updateRequestSequence += 1;
    modelRequestSequence += 1;
    useSettingsStore.setState({
      aiSettings: null,
      ollamaModels: [],
      openRouterModels: [],
      lmStudioModels: [],
      groqModels: [],
      loading: false,
      error: null,
    });
  };
  window.addEventListener('aac:auth-logout', resetForAuthContextChange);
  window.addEventListener('aac:auth-context-changed', resetForAuthContextChange);
}
