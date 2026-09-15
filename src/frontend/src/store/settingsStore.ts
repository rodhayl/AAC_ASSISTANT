import { create } from 'zustand';
import api, { extractError } from '../lib/api';
import i18n from '../i18n/index';

export type AiProviderId = 'ollama' | 'openrouter' | 'lmstudio' | 'groq';
/** The four endpoints that expose a model list. */
export type ModelEndpointId = AiProviderId;

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

const MODEL_ENDPOINTS: ModelEndpointId[] = ['ollama', 'openrouter', 'lmstudio', 'groq'];

function emptyPerEndpoint<T>(value: T): Record<ModelEndpointId, T> {
  return {
    ollama: value,
    openrouter: value,
    lmstudio: value,
    groq: value,
  };
}

interface SettingsState {
  aiSettings: AISettings | null;
  ollamaModels: OllamaModel[];
  openRouterModels: OpenRouterModel[];
  lmStudioModels: OpenRouterModel[];
  groqModels: OpenRouterModel[];
  /** Loading state for the AI *settings* resource only (GET/PUT /settings/ai). */
  loading: boolean;
  error: string | null;
  /**
   * Per-endpoint model-list state (A18). A single shared sequence/spinner let
   * one provider's fetch invalidate another's (the losing list stayed `[]`) and
   * made a model fetch block the settings spinner.
   */
  modelLoading: Record<ModelEndpointId, boolean>;
  modelError: Record<ModelEndpointId, string | null>;

  // Actions
  fetchAISettings: () => Promise<void>;
  updateAISettings: (settings: Partial<AISettings>) => Promise<void>;
  fetchOllamaModels: () => Promise<void>;
  fetchOpenRouterModels: (apiKey?: string) => Promise<void>;
  fetchLmStudioModels: () => Promise<void>;
  fetchGroqModels: (apiKey?: string) => Promise<void>;
}

// One sequence per endpoint: a newer request only invalidates requests to the
// *same* endpoint.
let modelRequestSequences: Record<ModelEndpointId, number> = emptyPerEndpoint(0);
let settingsRequestSequence = 0;
let updateRequestSequence = 0;
// Serializes overlapping autosaves so two rapid edits cannot land out of order
// (A18). Each update waits for the previous one to settle.
let updateChain: Promise<unknown> = Promise.resolve();

export const useSettingsStore = create<SettingsState>((set) => {
  // The four model-fetch actions share one load-and-store shape; only the
  // endpoint, element type, and failure message differ. A newer request for the
  // same endpoint wins. The list is typed per endpoint and guarded at runtime: a
  // missing/non-array ``models`` payload becomes an empty list (never
  // ``undefined``), so consumers calling ``.find``/``.length`` on the stored
  // list cannot crash on a shape drift. The publish is skipped entirely when a
  // newer request for the same endpoint already owns the state.
  const fetchModelList = async <T>(
    id: ModelEndpointId,
    endpoint: string,
    failureMessage: string,
    publish: (models: T[]) => void,
    headers?: Record<string, string>,
  ): Promise<void> => {
    const requestId = ++modelRequestSequences[id];
    set((state) => ({
      modelLoading: { ...state.modelLoading, [id]: true },
      modelError: { ...state.modelError, [id]: null },
    }));
    try {
      const response = headers
        ? await api.get<{ models?: T[] }>(endpoint, { headers })
        : await api.get<{ models?: T[] }>(endpoint);
      if (requestId !== modelRequestSequences[id]) return;
      const models = response.data?.models;
      publish(Array.isArray(models) ? models : []);
      set((state) => ({ modelLoading: { ...state.modelLoading, [id]: false } }));
    } catch (error: unknown) {
      if (requestId !== modelRequestSequences[id]) return;
      set((state) => ({
        modelLoading: { ...state.modelLoading, [id]: false },
        modelError: { ...state.modelError, [id]: extractError(error, failureMessage) },
      }));
    }
  };

  const doUpdateAISettings = async (settings: Partial<AISettings>) => {
    const requestId = ++updateRequestSequence;
    set({ loading: true, error: null });
    try {
      await api.put('/settings/ai', settings);
      // Re-read the canonical values in this same operation and settle the
      // spinner here: relying on the inner fetchAISettings to clear it left
      // ``loading`` stuck whenever that fetch early-returned as stale (A18).
      const fetchId = ++settingsRequestSequence;
      const response = await api.get('/settings/ai');
      if (fetchId !== settingsRequestSequence) return;
      set({ aiSettings: response.data, loading: false, error: null });
    } catch (error: unknown) {
      if (requestId !== updateRequestSequence) return;
      const message = extractError(error, tSettings('settings:ai.updateFailed'));
      set({ error: message, loading: false });
      throw error;
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
    modelLoading: emptyPerEndpoint(false),
    modelError: emptyPerEndpoint<string | null>(null),

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
      // Serialize autosaves: a 500 ms debounce plus an unguarded PUT let two
      // rapid edits reach the server out of order (A18).
      const run = updateChain.then(() => doUpdateAISettings(settings));
      updateChain = run.catch(() => undefined);
      return run;
    },

    fetchOllamaModels: async () => {
      await fetchModelList<OllamaModel>(
        'ollama',
        '/settings/ai/models/ollama',
        tSettings('settings:ai.fetchOllamaFailed'),
        (models) => set({ ollamaModels: models }),
      );
    },

    fetchOpenRouterModels: async (apiKey?: string) => {
      const headers = apiKey?.trim()
        ? { 'X-OpenRouter-API-Key': apiKey.trim() }
        : undefined;
      await fetchModelList<OpenRouterModel>(
        'openrouter',
        '/settings/ai/models/openrouter',
        tSettings('settings:ai.fetchOpenRouterFailed'),
        (models) => set({ openRouterModels: models }),
        headers,
      );
    },

    fetchLmStudioModels: async () => {
      await fetchModelList<OpenRouterModel>(
        'lmstudio',
        '/settings/ai/models/lmstudio',
        tSettings('settings:ai.fetchLmStudioFailed'),
        (models) => set({ lmStudioModels: models }),
      );
    },

    fetchGroqModels: async (apiKey?: string) => {
      const headers = apiKey?.trim()
        ? { 'X-Groq-API-Key': apiKey.trim() }
        : undefined;
      await fetchModelList<OpenRouterModel>(
        'groq',
        '/settings/ai/models/groq',
        tSettings('settings:ai.fetchGroqFailed'),
        (models) => set({ groqModels: models }),
        headers,
      );
    },
  };
});

if (typeof window !== 'undefined') {
  const resetForAuthContextChange = () => {
    settingsRequestSequence += 1;
    updateRequestSequence += 1;
    modelRequestSequences = emptyPerEndpoint(0);
    updateChain = Promise.resolve();
    useSettingsStore.setState({
      aiSettings: null,
      ollamaModels: [],
      openRouterModels: [],
      lmStudioModels: [],
      groqModels: [],
      loading: false,
      error: null,
      modelLoading: emptyPerEndpoint(false),
      modelError: emptyPerEndpoint<string | null>(null),
    });
  };
  window.addEventListener('aac:auth-logout', resetForAuthContextChange);
  window.addEventListener('aac:auth-context-changed', resetForAuthContextChange);
}

export { MODEL_ENDPOINTS };
