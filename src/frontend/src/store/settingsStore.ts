import { create } from 'zustand';
import api from '../lib/api';

interface AISettings {
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

interface OllamaModel {
  name: string;
  size?: number;
  modified_at?: string;
}

interface OpenRouterModel {
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
  fallbackAISettings: AISettings | null;
  ollamaModels: OllamaModel[];
  openRouterModels: OpenRouterModel[];
  lmStudioModels: OpenRouterModel[];
  loading: boolean;
  error: string | null;

  // Actions
  fetchAISettings: () => Promise<void>;
  updateAISettings: (settings: Partial<AISettings>) => Promise<void>;
  fetchFallbackAISettings: () => Promise<void>;
  updateFallbackAISettings: (settings: Partial<AISettings>) => Promise<void>;
  fetchOllamaModels: (useFallback?: boolean) => Promise<void>;
  fetchOpenRouterModels: (useFallback?: boolean) => Promise<void>;
  fetchLmStudioModels: (useFallback?: boolean) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  aiSettings: null,
  fallbackAISettings: null,
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
      const err = error as { response?: { data?: { detail?: string } }, message?: string };
      const message = err.response?.data?.detail || err.message || 'Failed to fetch AI settings';
      set({ error: message, loading: false });
    }
  },

  fetchFallbackAISettings: async () => {
    set({ loading: true, error: null });
    try {
      const response = await api.get('/settings/ai/fallback');
      set({ fallbackAISettings: response.data, loading: false });
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }, message?: string };
      const message = err.response?.data?.detail || err.message || 'Failed to fetch fallback AI settings';
      set({ error: message, loading: false });
    }
  },

  updateAISettings: async (settings: Partial<AISettings>) => {
    set({ loading: true, error: null });
    try {
      await api.put('/settings/ai', settings);
      await get().fetchAISettings();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }, message?: string };
      const message = err.response?.data?.detail || err.message || 'Failed to update settings';
      set({ error: message, loading: false });
      throw error;
    }
  },

  updateFallbackAISettings: async (settings: Partial<AISettings>) => {
    set({ loading: true, error: null });
    try {
      await api.put('/settings/ai/fallback', settings);
      await get().fetchFallbackAISettings();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }, message?: string };
      const message = err.response?.data?.detail || err.message || 'Failed to update fallback settings';
      set({ error: message, loading: false });
      throw error;
    }
  },

  fetchOllamaModels: async (useFallback = false) => {
    set({ loading: true, error: null });
    try {
      const response = await api.get('/settings/ai/models/ollama', {
        params: useFallback ? { use_fallback: true } : undefined,
      });
      set({ ollamaModels: response.data.models, loading: false });
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }, message?: string };
      const message = err.response?.data?.detail || err.message || 'Failed to fetch Ollama models';
      set({ error: message, loading: false });
    }
  },

  fetchOpenRouterModels: async (useFallback = false) => {
    set({ loading: true, error: null });
    try {
      const response = await api.get('/settings/ai/models/openrouter', {
        params: useFallback ? { use_fallback: true } : undefined,
      });
      set({ openRouterModels: response.data.models, loading: false });
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }, message?: string };
      const message = err.response?.data?.detail || err.message || 'Failed to fetch OpenRouter models';
      set({ error: message, loading: false });
    }
  },

  fetchLmStudioModels: async (useFallback = false) => {
    set({ loading: true, error: null });
    try {
      const response = await api.get('/settings/ai/models/lmstudio', {
        params: useFallback ? { use_fallback: true } : undefined,
      });
      set({ lmStudioModels: response.data.models, loading: false });
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }, message?: string };
      const message = err.response?.data?.detail || err.message || 'Failed to fetch LM Studio models';
      set({ error: message, loading: false });
    }
  },
}));
