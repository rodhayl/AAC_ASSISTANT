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

export const useSettingsStore = create<SettingsState>((set, get) => {
  // The three model-fetch actions share one load-and-store shape; only the
  // endpoint, state key, and failure message differ.
  const fetchModelList = async (
    endpoint: string,
    stateKey: 'ollamaModels' | 'openRouterModels' | 'lmStudioModels' | 'groqModels',
    failureMessage: string,
    headers?: Record<string, string>
  ) => {
    set({ loading: true, error: null });
    try {
      const response = headers
        ? await api.get(endpoint, { headers })
        : await api.get(endpoint);
      set({ [stateKey]: response.data.models, loading: false });
    } catch (error: unknown) {
      const message = extractError(error, failureMessage);
      set({ error: message, loading: false });
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
      set({ loading: true, error: null });
      try {
        const response = await api.get('/settings/ai');
        set({ aiSettings: response.data, loading: false });
      } catch (error: unknown) {
        const message = extractError(error, tSettings('settings:ai.fetchFailed'));
        set({ error: message, loading: false });
      }
    },

    updateAISettings: async (settings: Partial<AISettings>) => {
      set({ loading: true, error: null });
      try {
        await api.put('/settings/ai', settings);
        await get().fetchAISettings();
      } catch (error: unknown) {
        const message = extractError(error, tSettings('settings:ai.updateFailed'));
        set({ error: message, loading: false });
        throw error;
      }
    },

    fetchOllamaModels: async () => {
      await fetchModelList('/settings/ai/models/ollama', 'ollamaModels', tSettings('settings:ai.fetchOllamaFailed'));
    },

    fetchOpenRouterModels: async (apiKey?: string) => {
      const headers = apiKey?.trim()
        ? { 'X-OpenRouter-API-Key': apiKey.trim() }
        : undefined;
      await fetchModelList(
        '/settings/ai/models/openrouter',
        'openRouterModels',
        tSettings('settings:ai.fetchOpenRouterFailed'),
        headers,
      );
    },

    fetchLmStudioModels: async () => {
      await fetchModelList('/settings/ai/models/lmstudio', 'lmStudioModels', tSettings('settings:ai.fetchLmStudioFailed'));
    },

    fetchGroqModels: async (apiKey?: string) => {
      const headers = apiKey?.trim()
        ? { 'X-Groq-API-Key': apiKey.trim() }
        : undefined;
      await fetchModelList(
        '/settings/ai/models/groq',
        'groqModels',
        tSettings('settings:ai.fetchGroqFailed'),
        headers,
      );
    },
  };
});
