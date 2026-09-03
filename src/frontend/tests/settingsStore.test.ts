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
    ['fetchOllamaModels', '/settings/ai/models/ollama', 'ollamaModels', 'No se pudieron obtener los modelos de Ollama'],
    ['fetchOpenRouterModels', '/settings/ai/models/openrouter', 'openRouterModels', 'No se pudieron obtener los modelos de OpenRouter'],
    ['fetchLmStudioModels', '/settings/ai/models/lmstudio', 'lmStudioModels', 'No se pudieron obtener los modelos de LM Studio'],
  ] as const)(
    '%s stores the model list',
    async (action, endpoint, stateKey, failureMessage) => {
      (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { models: [{ name: 'model-a' }] },
      });

      await useSettingsStore.getState()[action]();

      expect(api.get).toHaveBeenCalledWith(endpoint);
      expect(useSettingsStore.getState()[stateKey]).toEqual([{ name: 'model-a' }]);
      expect(useSettingsStore.getState().error).toBeNull();

      // Failure path records the message and clears loading.
      (api.get as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('down'));
      await useSettingsStore.getState()[action]();
      expect(useSettingsStore.getState().error).toBe(failureMessage);
      expect(useSettingsStore.getState().loading).toBe(false);
    },
  );

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
    expect(useSettingsStore.getState().loading).toBe(false);

    resolveFirst?.({ data: { models: [{ id: 'old-model' }] } });
    await firstRequest;
    expect(useSettingsStore.getState().openRouterModels).toEqual([{ id: 'new-model' }]);
    expect(useSettingsStore.getState().loading).toBe(false);
    expect(api.get).toHaveBeenNthCalledWith(1, '/settings/ai/models/openrouter', {
      headers: { 'X-OpenRouter-API-Key': 'old-key' },
    });
    expect(api.get).toHaveBeenNthCalledWith(2, '/settings/ai/models/openrouter', {
      headers: { 'X-OpenRouter-API-Key': 'new-key' },
    });
  });
});
