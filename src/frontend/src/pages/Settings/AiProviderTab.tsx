import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, Cloud, Cpu } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { useSettingsStore } from '../../store/settingsStore';
import type { AISettings } from '../../store/settingsStore';
import { config } from '../../config';
import { useAutoHide } from '../../hooks/useAutoHide';
import api, { extractError } from '../../lib/api';
import type { AiOverride, ProviderHealth } from './types';
import { AiProviderFields } from './AiProviderFields';

export function AiProviderTab() {
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('settings');
  const aiSettings = useSettingsStore((state) => state.aiSettings)
  const ollamaModels = useSettingsStore((state) => state.ollamaModels)
  const openRouterModels = useSettingsStore((state) => state.openRouterModels)
  const lmStudioModels = useSettingsStore((state) => state.lmStudioModels)
  const loading = useSettingsStore((state) => state.loading)
  const error = useSettingsStore((state) => state.error)
  const fetchAISettings = useSettingsStore((state) => state.fetchAISettings)
  const updateAISettings = useSettingsStore((state) => state.updateAISettings)
  const fetchOllamaModels = useSettingsStore((state) => state.fetchOllamaModels)
  const fetchOpenRouterModels = useSettingsStore((state) => state.fetchOpenRouterModels)
  const fetchLmStudioModels = useSettingsStore((state) => state.fetchLmStudioModels)
  const isAdmin = user?.user_type === 'admin';
  const [aiOverride, setAiOverride] = useState<AiOverride>({});
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [modelSearchOpen, setModelSearchOpen] = useState(false);
  const [modelSearchQuery, setModelSearchQuery] = useState('');
  const [health, setHealth] = useState<ProviderHealth | null>(null);
  const lastSavedSettingsRef = useRef('');
  const [readOnlyState, setReadOnlyState] = useState<{
    requestKey: string;
    settings: AISettings | null;
    loading: boolean;
    error: string | null;
  } | null>(null);
  const userId = user?.id;
  const userRole = user?.user_type;
  const readOnlyRequestKey = `${userId ?? 'none'}:${userRole ?? 'none'}`;

  useAutoHide(saveSuccess, () => setSaveSuccess(false));

  useEffect(() => {
    if (!userId) return;
    if (isAdmin) {
      fetchAISettings();
      return;
    }

    // Non-admins use the read-only response directly. Avoid issuing the same
    // request through both the store and this component.
    let active = true;
    const controller = new AbortController();

    api
      .get('/settings/ai', { signal: controller.signal })
      .then((response) => {
        if (active) {
          setReadOnlyState({
            requestKey: readOnlyRequestKey,
            settings: response.data,
            loading: false,
            error: null,
          });
        }
      })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) {
          setReadOnlyState({
            requestKey: readOnlyRequestKey,
            settings: null,
            loading: false,
            error: extractError(requestError, t('ai.loadFailed')),
          });
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [userId, userRole, isAdmin, fetchAISettings, readOnlyRequestKey, t]);

  const currentAiProvider = aiOverride.provider ?? aiSettings?.provider ?? 'ollama';
  const currentOllamaModel = aiOverride.ollama_model ?? aiSettings?.ollama_model ?? '';
  const currentOpenRouterModel = aiOverride.openrouter_model ?? aiSettings?.openrouter_model ?? '';
  const currentLmStudioModel = aiOverride.lmstudio_model ?? aiSettings?.lmstudio_model ?? '';
  const currentSelectedModel =
    currentAiProvider === 'ollama'
      ? currentOllamaModel
      : currentAiProvider === 'lmstudio'
        ? currentLmStudioModel
        : currentOpenRouterModel;
  const currentOpenRouterApiKey = aiOverride.openrouter_api_key ?? aiSettings?.openrouter_api_key ?? '';
  const currentOllamaBaseUrl = aiOverride.ollama_base_url ?? aiSettings?.ollama_base_url ?? config.OLLAMA_BASE_URL;
  const currentLmStudioBaseUrl =
    aiOverride.lmstudio_base_url ?? aiSettings?.lmstudio_base_url ?? config.LMSTUDIO_BASE_URL;
  const currentMaxTokens = aiOverride.max_tokens ?? aiSettings?.max_tokens ?? config.AI_MAX_TOKENS;
  const currentTemperature = aiOverride.temperature ?? aiSettings?.temperature ?? config.AI_TEMPERATURE;
  const readOnlyForCurrentUser =
    !isAdmin && readOnlyState?.requestKey === readOnlyRequestKey;
  const visibleAiSettings = isAdmin
    ? aiSettings
    : readOnlyForCurrentUser
      ? readOnlyState?.settings ?? null
      : null;
  const readOnlyLoading =
    !isAdmin && Boolean(userId) && (!readOnlyForCurrentUser || readOnlyState?.loading === true);
  const readOnlyError = readOnlyForCurrentUser ? readOnlyState?.error ?? null : null;
  const selectedHealth =
    currentAiProvider === 'ollama'
      ? health?.ollama
      : currentAiProvider === 'openrouter'
        ? health?.openrouter
        : health?.lmstudio;
  const selectedProviderLabel =
    currentAiProvider === 'ollama'
      ? t('ai.ollama')
      : currentAiProvider === 'openrouter'
        ? t('ai.openrouter')
        : t('ai.lmstudio', 'LM Studio');

  const selectedProviderStatusMessage = (() => {
    if (!selectedHealth) return null;
    if (selectedHealth.available) {
      return t('ai.providerReady', `${selectedProviderLabel} is available and responding.`);
    }
    if (currentAiProvider === 'openrouter') {
      if (selectedHealth.reason === 'api_key_missing' || !currentOpenRouterApiKey.trim()) {
        return t('ai.openrouterApiKeyMissing', 'OpenRouter API key is missing.');
      }
      return t(
        'ai.openrouterUnavailable',
        'OpenRouter is configured but did not respond. Check the API key, account, or network.'
      );
    }
    if (currentAiProvider === 'lmstudio') {
      return t('ai.lmstudioUnavailable', 'LM Studio is not reachable at the configured base URL.');
    }
    return t('ai.ollamaUnavailable', 'Ollama is not reachable at the configured base URL.');
  })();

  useEffect(() => {
    if (!isAdmin) return;
    if (currentAiProvider === 'ollama' && ollamaModels.length === 0) {
      fetchOllamaModels();
    } else if (currentAiProvider === 'openrouter' && openRouterModels.length === 0) {
      fetchOpenRouterModels();
    } else if (currentAiProvider === 'lmstudio' && lmStudioModels.length === 0) {
      fetchLmStudioModels();
    }
  }, [
    isAdmin,
    currentAiProvider,
    ollamaModels.length,
    openRouterModels.length,
    lmStudioModels.length,
    fetchOllamaModels,
    fetchOpenRouterModels,
    fetchLmStudioModels,
  ]);

  const handleFetchModels = async () => {
    try {
      if (currentAiProvider === 'ollama') {
        await fetchOllamaModels();
      } else if (currentAiProvider === 'openrouter') {
        await fetchOpenRouterModels(currentOpenRouterApiKey);
      } else {
        await fetchLmStudioModels();
      }
    } catch (err) {
      console.error('Failed to fetch models:', err);
    }
  };

  const buildSettingsPayload = useCallback((overrides: AiOverride) => ({
    provider: overrides.provider ?? aiSettings?.provider ?? 'ollama',
    ollama_model: overrides.ollama_model ?? aiSettings?.ollama_model ?? '',
    openrouter_model: overrides.openrouter_model ?? aiSettings?.openrouter_model ?? '',
    lmstudio_model: overrides.lmstudio_model ?? aiSettings?.lmstudio_model ?? '',
    openrouter_api_key: overrides.openrouter_api_key ?? aiSettings?.openrouter_api_key ?? '',
    ollama_base_url: overrides.ollama_base_url ?? aiSettings?.ollama_base_url ?? config.OLLAMA_BASE_URL,
    lmstudio_base_url: overrides.lmstudio_base_url ?? aiSettings?.lmstudio_base_url ?? config.LMSTUDIO_BASE_URL,
    max_tokens: overrides.max_tokens ?? aiSettings?.max_tokens ?? config.AI_MAX_TOKENS,
    temperature: overrides.temperature ?? aiSettings?.temperature ?? config.AI_TEMPERATURE,
  }), [aiSettings]);

  const persistSettings = useCallback(async (overrides: AiOverride) => {
    const payload = buildSettingsPayload(overrides);
    const signature = JSON.stringify(payload);
    lastSavedSettingsRef.current = signature;
    try {
      await updateAISettings(payload);
      setSaveSuccess(true);
    } catch (err) {
      if (lastSavedSettingsRef.current === signature) {
        lastSavedSettingsRef.current = '';
      }
      console.error('Failed to save settings:', err);
    }
  }, [buildSettingsPayload, updateAISettings]);

  useEffect(() => {
    if (!isAdmin || Object.keys(aiOverride).length === 0) return;

    const payload = buildSettingsPayload(aiOverride);
    const signature = JSON.stringify(payload);
    if (signature === lastSavedSettingsRef.current) return;

    // Persist every AI change after a short pause, including model selection,
    // so controls cannot remain as unsaved local state.
    const timer = setTimeout(() => {
      void persistSettings(aiOverride);
    }, 500);
    return () => clearTimeout(timer);
  }, [aiOverride, buildSettingsPayload, isAdmin, persistSettings]);

  const checkHealth = async () => {
    try {
      const response = await api.get('/providers/health');
      setHealth(response.data);
    } catch {
      // Provider health is optional and may be unavailable.
    }
  };

  if (!isAdmin) {
    return (
      <section
        id="settings-ai"
        aria-labelledby="settings-ai-heading"
        className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
      >
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h3 id="settings-ai-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('ai.readOnlyTitle', 'AI Configuration')}
          </h3>
          <p className="text-sm text-gray-500 mt-1">{t('ai.viewOnly', 'Current AI settings (View only - contact admin to change)')}</p>
        </div>
        {readOnlyLoading && (
          <div className="p-6 text-sm text-gray-500">{t('ai.loading', 'Loading AI settings...')}</div>
        )}
        {readOnlyError && (
          <div className="p-6 text-sm text-red-600" role="alert">
            {readOnlyError}
          </div>
        )}
        {visibleAiSettings && !readOnlyLoading && (
          <div className="p-6 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="block text-sm font-medium text-gray-700 mb-1">{t('ai.primaryProvider', 'Primary Provider')}</p>
                <div className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg capitalize flex items-center">
                  {visibleAiSettings.provider === 'ollama' ? (
                    <Cpu className="w-4 h-4 mr-2 text-indigo-600" />
                  ) : (
                    <Cloud className="w-4 h-4 mr-2 text-indigo-600" />
                  )}
                  {visibleAiSettings.provider}
                </div>
              </div>
              <div>
                <p className="block text-sm font-medium text-gray-700 mb-1">{t('ai.primaryModel', 'Primary Model')}</p>
                <div className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg">
                  {(visibleAiSettings.provider === 'ollama'
                    ? visibleAiSettings.ollama_model
                    : visibleAiSettings.provider === 'lmstudio'
                      ? visibleAiSettings.lmstudio_model
                      : visibleAiSettings.openrouter_model) || t('ai.notConfigured', 'Not configured')}
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    );
  }

  return (
    <section
      id="settings-ai"
      aria-labelledby="settings-ai-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 id="settings-ai-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {t('ai.title')}
            </h3>
            <p className="text-sm text-gray-500 mt-1">{t('ai.subtitle')}</p>
          </div>
          {saveSuccess && <div className="text-green-600 text-sm font-medium">{t('ai.saveOk')}</div>}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
            <AlertCircle className="w-5 h-5 mr-2" />
            {error}
          </div>
        )}
        <div>
          <p className="block text-sm font-medium text-gray-700 mb-3">{t('ai.primary')}</p>
          <div className="grid grid-cols-2 gap-4">
            <button
              type="button"
              onClick={() => setAiOverride((prev) => ({ ...prev, provider: 'ollama' }))}
              className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${
                currentAiProvider === 'ollama'
                  ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30'
                  : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
              }`}
            >
              <Cpu className="w-6 h-6 text-indigo-600" />
              <div className="text-left">
                <div className="font-medium text-gray-900 dark:text-gray-100">{t('ai.ollama')}</div>
                <div className="text-xs text-gray-600 dark:text-gray-400">{t('ai.ollamaDesc')}</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setAiOverride((prev) => ({ ...prev, provider: 'openrouter' }))}
              className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${
                currentAiProvider === 'openrouter'
                  ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30'
                  : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
              }`}
            >
              <Cloud className="w-6 h-6 text-indigo-600" />
              <div className="text-left">
                <div className="font-medium text-gray-900 dark:text-gray-100">{t('ai.openrouter')}</div>
                <div className="text-xs text-gray-600 dark:text-gray-400">{t('ai.openrouterDesc')}</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setAiOverride((prev) => ({ ...prev, provider: 'lmstudio' }))}
              className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${
                currentAiProvider === 'lmstudio'
                  ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30'
                  : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
              }`}
            >
              <Cpu className="w-6 h-6 text-indigo-600" />
              <div className="text-left">
                <div className="font-medium text-gray-900 dark:text-gray-100">{t('ai.lmstudio', 'LM Studio')}</div>
                <div className="text-xs text-gray-600 dark:text-gray-400">{t('ai.localOpenAIAPI', 'Local OpenAI-API')}</div>
              </div>
            </button>
          </div>
        </div>

        <AiProviderFields
          provider={currentAiProvider}
          lmStudioModel={currentLmStudioModel}
          selectedModel={currentSelectedModel}
          openRouterApiKey={currentOpenRouterApiKey}
          ollamaBaseUrl={currentOllamaBaseUrl}
          lmStudioBaseUrl={currentLmStudioBaseUrl}
          maxTokens={currentMaxTokens}
          temperature={currentTemperature}
          ollamaModels={ollamaModels}
          openRouterModels={openRouterModels}
          lmStudioModels={lmStudioModels}
          loading={loading}
          setAiOverride={setAiOverride}
          modelSearchOpen={modelSearchOpen}
          setModelSearchOpen={setModelSearchOpen}
          modelSearchQuery={modelSearchQuery}
          setModelSearchQuery={setModelSearchQuery}
          onFetchModels={handleFetchModels}
        />

        <div className="flex items-center gap-2 pt-4 border-t border-gray-200">
          <button type="button" onClick={checkHealth} className="px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
            {t('ai.health')}
          </button>
        </div>
        {selectedHealth && (
          <div
            className={`rounded-lg border px-4 py-3 text-sm ${
              selectedHealth.available
                ? 'border-green-200 bg-green-50 text-green-800'
                : 'border-red-200 bg-red-50 text-red-800'
            }`}
          >
            <div className="font-medium">
              {selectedProviderLabel}:{' '}
              <span className={selectedHealth.available ? 'text-green-700' : 'text-red-700'}>
                {selectedHealth.available ? t('ai.statusUp', 'ok') : t('ai.statusDown', 'down')}
              </span>
            </div>
            {selectedProviderStatusMessage && (
              <div className="mt-1 text-xs">
                {selectedProviderStatusMessage}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end pt-6 border-t border-gray-200">
          <p className="text-sm text-gray-500">
            {t('ai.autoSave', 'AI settings are saved automatically.')}
          </p>
        </div>
      </div>
    </section>
  );
}
