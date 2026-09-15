import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
  extractError: (_error: unknown, fallback: string) => fallback,
}));

import api from '../src/lib/api';
import { useSettingsStore } from '../src/store/settingsStore';

describe('settings store', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSettingsStore.setState({
      aiSettings: null,
      ollamaModels: [],
      openRouterModels: [],
      lmStudioModels: [],
      loading: false,
      error: null,
      modelLoading: { ollama: false, openrouter: false, lmstudio: false, groq: false },
      modelError: { ollama: null, openrouter: null, lmstudio: null, groq: null },
    });
  });

  it('fetches AI settings and stores them', async () => {
    const aiSettings = { provider: 'ollama', can_edit: true };
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: aiSettings });

    await useSettingsStore.getState().fetchAISettings();

    expect(api.get).toHaveBeenCalledWith('/settings/ai');
    expect(useSettingsStore.getState().aiSettings).toEqual(aiSettings);
    expect(useSettingsStore.getState().loading).toBe(false);
  });

  it('records an error when fetching AI settings fails', async () => {
    (api.get as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));

    await useSettingsStore.getState().fetchAISettings();

    // The store localizes its failure messages through the real (es) i18n
    // instance, which is initialized in the test environment.
    expect(useSettingsStore.getState().error).toBe('No se pudieron obtener los ajustes de IA');
    expect(useSettingsStore.getState().aiSettings).toBeNull();
  });

  it('updates AI settings then re-fetches the canonical values', async () => {
    (api.put as ReturnType<typeof vi.fn>).mockResolvedValue({});
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { provider: 'openrouter', can_edit: true },
    });

    await useSettingsStore.getState().updateAISettings({ provider: 'openrouter' });

    expect(api.put).toHaveBeenCalledWith('/settings/ai', { provider: 'openrouter' });
    expect(useSettingsStore.getState().aiSettings?.provider).toBe('openrouter');
  });

  it('surfaces update failures and rethrows', async () => {
    (api.put as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('denied'));

    await expect(
      useSettingsStore.getState().updateAISettings({ provider: 'ollama' }),
    ).rejects.toThrow('denied');
    expect(useSettingsStore.getState().error).toBe('No se pudieron actualizar los ajustes');
  });

  it.each([
    ['fetchOllamaModels', 'ollama', '/settings/ai/models/ollama', 'ollamaModels', 'No se pudieron obtener los modelos de Ollama'],
    ['fetchOpenRouterModels', 'openrouter', '/settings/ai/models/openrouter', 'openRouterModels', 'No se pudieron obtener los modelos de OpenRouter'],
    ['fetchLmStudioModels', 'lmstudio', '/settings/ai/models/lmstudio', 'lmStudioModels', 'No se pudieron obtener los modelos de LM Studio'],
  ] as const)(
    '%s stores the model list',
    async (action, endpointId, endpoint, stateKey, failureMessage) => {
      (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { models: [{ name: 'model-a' }] },
      });

      await useSettingsStore.getState()[action]();

      expect(api.get).toHaveBeenCalledWith(endpoint);
      expect(useSettingsStore.getState()[stateKey]).toEqual([{ name: 'model-a' }]);
      expect(useSettingsStore.getState().modelError[endpointId]).toBeNull();

      // Failure path records the message on its own endpoint and clears that
      // endpoint's loading flag (A18: no shared spinner/error).
      (api.get as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('down'));
      await useSettingsStore.getState()[action]();
      expect(useSettingsStore.getState().modelError[endpointId]).toBe(failureMessage);
      expect(useSettingsStore.getState().modelLoading[endpointId]).toBe(false);
      // The settings resource state is untouched by a model-list failure.
      expect(useSettingsStore.getState().loading).toBe(false);
      expect(useSettingsStore.getState().error).toBeNull();
    },
  );

  it('keeps one endpoint\u2019s fetch from invalidating another\u2019s (A18)', async () => {
    let releaseOllama: ((value: { data: { models: Array<{ name: string }> } }) => void) | undefined;
    (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === '/settings/ai/models/ollama') {
        return new Promise((resolve) => {
          releaseOllama = resolve;
        });
      }
      return Promise.resolve({ data: { models: [{ id: 'groq-model' }] } });
    });

    const ollamaRequest = useSettingsStore.getState().fetchOllamaModels();
    expect(useSettingsStore.getState().modelLoading.ollama).toBe(true);

    // A second endpoint finishes while the first is still in flight; it must
    // not cancel the Ollama request nor clear its loading flag.
    await useSettingsStore.getState().fetchGroqModels();
    expect(useSettingsStore.getState().groqModels).toEqual([{ id: 'groq-model' }]);
    expect(useSettingsStore.getState().modelLoading.ollama).toBe(true);

    releaseOllama?.({ data: { models: [{ name: 'ollama-model' }] } });
    await ollamaRequest;
    expect(useSettingsStore.getState().ollamaModels).toEqual([{ name: 'ollama-model' }]);
    expect(useSettingsStore.getState().modelLoading.ollama).toBe(false);
  });

  it('serializes overlapping autosaves so the last edit lands last (A18)', async () => {
    const putOrder: string[] = [];
    let releaseFirst: (() => void) | undefined;
    (api.put as ReturnType<typeof vi.fn>).mockImplementation((_url: string, body: { provider?: string }) => {
      putOrder.push(body.provider ?? 'unknown');
      if (putOrder.length === 1) {
        return new Promise((resolve) => {
          releaseFirst = () => resolve({});
        });
      }
      return Promise.resolve({});
    });
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { provider: 'groq', can_edit: true },
    });

    const first = useSettingsStore.getState().updateAISettings({ provider: 'ollama' });
    const second = useSettingsStore.getState().updateAISettings({ provider: 'groq' });

    // The second PUT must not be issued until the first settles: after both
    // calls, only the first request has left the client.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(putOrder).toEqual(['ollama']);
    releaseFirst?.();
    await Promise.all([first, second]);
    expect(putOrder).toEqual(['ollama', 'groq']);
    expect(useSettingsStore.getState().loading).toBe(false);
  });

  it('keeps the newest model-list response when requests overlap', async () => {
    let resolveFirst: ((value: { data: { models: Array<{ id: string }> } }) => void) | undefined;
    let resolveSecond: ((value: { data: { models: Array<{ id: string }> } }) => void) | undefined;
    let requests = 0;
    (api.get as ReturnType<typeof vi.fn>).mockImplementation(() => {
      requests += 1;
      return new Promise<{ data: { models: Array<{ id: string }> } }>((resolve) => {
        if (requests === 1) resolveFirst = resolve;
        else resolveSecond = resolve;
      });
    });

    const firstRequest = useSettingsStore.getState().fetchOpenRouterModels('old-key');
    const secondRequest = useSettingsStore.getState().fetchOpenRouterModels('new-key');

    resolveSecond?.({ data: { models: [{ id: 'new-model' }] } });
    await secondRequest;
    expect(useSettingsStore.getState().openRouterModels).toEqual([{ id: 'new-model' }]);
    expect(useSettingsStore.getState().modelLoading.openrouter).toBe(false);

    resolveFirst?.({ data: { models: [{ id: 'old-model' }] } });
    await firstRequest;
    expect(useSettingsStore.getState().openRouterModels).toEqual([{ id: 'new-model' }]);
    expect(useSettingsStore.getState().modelLoading.openrouter).toBe(false);
    expect(api.get).toHaveBeenNthCalledWith(1, '/settings/ai/models/openrouter', {
      headers: { 'X-OpenRouter-API-Key': 'old-key' },
    });
    expect(api.get).toHaveBeenNthCalledWith(2, '/settings/ai/models/openrouter', {
      headers: { 'X-OpenRouter-API-Key': 'new-key' },
    });
  });
});
