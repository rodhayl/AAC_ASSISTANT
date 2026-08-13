import { create } from 'zustand';
import api, { extractError } from '../lib/api';

export interface AISettings {
  provider: 'ollama' | 'openrouter' | 'lmstudio';
  ollama_model: string;
  openrouter_model: string;
  lmstudio_model: string;
  openrouter_api_key?: string;
  ollama_base_url: string;
  lmstudio_base_url: string;
  // Global LLM behavior controls
  max_tokens?: number;
  temperature?: number;
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

interface SettingsState {
  aiSettings: AISettings | null;
  ollamaModels: OllamaModel[];
  openRouterModels: OpenRouterModel[];
  lmStudioModels: OpenRouterModel[];
  loading: boolean;
  error: string | null;

  // Actions
  fetchAISettings: () => Promise<void>;
  updateAISettings: (settings: Partial<AISettings>) => Promise<void>;
  fetchOllamaModels: () => Promise<void>;
  fetchOpenRouterModels: () => Promise<void>;
  fetchLmStudioModels: () => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => {
  // The three model-fetch actions share one load-and-store shape; only the
  // endpoint, state key, and failure message differ.
  const fetchModelList = async (
    endpoint: string,
    stateKey: 'ollamaModels' | 'openRouterModels' | 'lmStudioModels',
    failureMessage: string
  ) => {
    set({ loading: true, error: null });
    try {
      const response = await api.get(endpoint);
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
    loading: false,
    error: null,

    fetchAISettings: async () => {
      set({ loading: true, error: null });
      try {
        const response = await api.get('/settings/ai');
        set({ aiSettings: response.data, loading: false });
      } catch (error: unknown) {
        const message = extractError(error, 'Failed to fetch AI settings');
        set({ error: message, loading: false });
      }
    },

    updateAISettings: async (settings: Partial<AISettings>) => {
      set({ loading: true, error: null });
      try {
        await api.put('/settings/ai', settings);
        await get().fetchAISettings();
      } catch (error: unknown) {
        const message = extractError(error, 'Failed to update settings');
        set({ error: message, loading: false });
        throw error;
      }
    },

    fetchOllamaModels: async () => {
      await fetchModelList('/settings/ai/models/ollama', 'ollamaModels', 'Failed to fetch Ollama models');
    },

    fetchOpenRouterModels: async () => {
      await fetchModelList('/settings/ai/models/openrouter', 'openRouterModels', 'Failed to fetch OpenRouter models');
    },

    fetchLmStudioModels: async () => {
      await fetchModelList('/settings/ai/models/lmstudio', 'lmStudioModels', 'Failed to fetch LM Studio models');
    },
  };
});
