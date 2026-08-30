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
import { StatusMessage } from '../../components/ui/StatusMessage';

export function AiProviderTab() {
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('settings');
  const aiSettings = useSettingsStore((state) => state.aiSettings)
  const ollamaModels = useSettingsStore((state) => state.ollamaModels)
  const openRouterModels = useSettingsStore((state) => state.openRouterModels)
  const lmStudioModels = useSettingsStore((state) => state.lmStudioModels)
  const groqModels = useSettingsStore((state) => state.groqModels)
  const loading = useSettingsStore((state) => state.loading)
  const error = useSettingsStore((state) => state.error)
  const fetchAISettings = useSettingsStore((state) => state.fetchAISettings)
  const updateAISettings = useSettingsStore((state) => state.updateAISettings)
  const fetchOllamaModels = useSettingsStore((state) => state.fetchOllamaModels)
  const fetchOpenRouterModels = useSettingsStore((state) => state.fetchOpenRouterModels)
  const fetchLmStudioModels = useSettingsStore((state) => state.fetchLmStudioModels)
  const fetchGroqModels = useSettingsStore((state) => state.fetchGroqModels)
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
  const currentGroqModel = aiOverride.groq_model ?? aiSettings?.groq_model ?? '';
  const currentSelectedModel =
    currentAiProvider === 'ollama'
      ? currentOllamaModel
      : currentAiProvider === 'lmstudio'
        ? currentLmStudioModel
        : currentAiProvider === 'groq'
          ? currentGroqModel
          : currentOpenRouterModel;
  const currentOpenRouterApiKey = aiOverride.openrouter_api_key ?? aiSettings?.openrouter_api_key ?? '';
  const currentGroqApiKey = aiOverride.groq_api_key ?? aiSettings?.groq_api_key ?? '';
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
        : currentAiProvider === 'groq'
          ? health?.groq
          : health?.lmstudio;
  const selectedProviderLabel =
    currentAiProvider === 'ollama'
      ? t('ai.ollama')
      : currentAiProvider === 'openrouter'
        ? t('ai.openrouter')
        : currentAiProvider === 'groq'
          ? t('ai.groq')
          : t('ai.lmstudio');

  const selectedProviderStatusMessage = (() => {
    if (!selectedHealth) return null;
    if (selectedHealth.available) {
      return t('ai.providerReady', {
        provider: selectedProviderLabel,
      });
    }
    if (currentAiProvider === 'openrouter') {
      if (selectedHealth.reason === 'api_key_missing' || !currentOpenRouterApiKey.trim()) {
        return t('ai.openrouterApiKeyMissing');
      }
      return t('ai.openrouterUnavailable');
    }
    if (currentAiProvider === 'lmstudio') {
      return t('ai.lmstudioUnavailable');
    }
    if (currentAiProvider === 'groq') {
      if (selectedHealth.reason === 'api_key_missing' || !currentGroqApiKey.trim()) {
        return t('ai.groqApiKeyMissing');
      }
      return t('ai.groqUnavailable');
    }
    return t('ai.ollamaUnavailable');
  })();

  useEffect(() => {
    if (!isAdmin) return;
    if (currentAiProvider === 'ollama' && ollamaModels.length === 0) {
      fetchOllamaModels();
    } else if (currentAiProvider === 'openrouter' && openRouterModels.length === 0) {
      fetchOpenRouterModels();
    } else if (currentAiProvider === 'lmstudio' && lmStudioModels.length === 0) {
      fetchLmStudioModels();
    } else if (currentAiProvider === 'groq' && groqModels.length === 0) {
      fetchGroqModels(currentGroqApiKey);
    }
  }, [
    isAdmin,
    currentAiProvider,
    ollamaModels.length,
    openRouterModels.length,
    lmStudioModels.length,
    groqModels.length,
    currentGroqApiKey,
    fetchOllamaModels,
    fetchOpenRouterModels,
    fetchLmStudioModels,
    fetchGroqModels,
  ]);

  const handleFetchModels = async () => {
    try {
      if (currentAiProvider === 'ollama') {
        await fetchOllamaModels();
      } else if (currentAiProvider === 'openrouter') {
        await fetchOpenRouterModels(currentOpenRouterApiKey);
      } else if (currentAiProvider === 'groq') {
        await fetchGroqModels(currentGroqApiKey);
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
    groq_model: overrides.groq_model ?? aiSettings?.groq_model ?? '',
    openrouter_api_key: overrides.openrouter_api_key ?? aiSettings?.openrouter_api_key ?? '',
    groq_api_key: overrides.groq_api_key ?? aiSettings?.groq_api_key ?? '',
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
        className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
      >
        <div className="p-6 border-b border-border">
          <h3 id="settings-ai-heading" className="text-lg font-semibold text-foreground">
            {t('ai.readOnlyTitle')}
          </h3>
          <p className="text-sm text-muted-foreground mt-1">{t('ai.viewOnly')}</p>
        </div>
        {readOnlyLoading && (
          <div className="p-6 text-sm text-muted-foreground">{t('ai.loading')}</div>
        )}
        {readOnlyError && (
          <div className="p-6 text-sm text-red-600 dark:text-red-400" role="alert">
            {readOnlyError}
          </div>
        )}
        {visibleAiSettings && !readOnlyLoading && (
          <div className="p-6 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="block text-sm font-medium text-foreground mb-1">{t('ai.primaryProvider')}</p>                    <div className="px-3 py-2 bg-muted border border-border rounded-lg capitalize flex items-center">
                  {visibleAiSettings.provider === 'ollama' ? (
                    <Cpu className="w-4 h-4 mr-2 text-brand" />
                  ) : (
                    <Cloud className="w-4 h-4 mr-2 text-brand" />
                  )}
                  {visibleAiSettings.provider}
                </div>
              </div>
              <div>
                <p className="block text-sm font-medium text-foreground mb-1">{t('ai.primaryModel')}</p>
                <div className="px-3 py-2 bg-muted border border-border rounded-lg">
                  {(visibleAiSettings.provider === 'ollama'
                    ? visibleAiSettings.ollama_model
                    : visibleAiSettings.provider === 'lmstudio'
                      ? visibleAiSettings.lmstudio_model
                      : visibleAiSettings.provider === 'groq'
                        ? visibleAiSettings.groq_model
                        : visibleAiSettings.openrouter_model) || t('ai.notConfigured')}
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
      className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
    >
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <div>
            <h3 id="settings-ai-heading" className="text-lg font-semibold text-foreground">
              {t('ai.title')}
            </h3>
            <p className="text-sm text-muted-foreground mt-1">{t('ai.subtitle')}</p>
          </div>
          {saveSuccess && <div className="text-green-600 dark:text-green-400 text-sm font-medium">{t('ai.saveOk')}</div>}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {error && (
          <StatusMessage variant="error" className="flex items-center">
            <AlertCircle className="w-5 h-5 mr-2" />
            {error}
          </StatusMessage>
        )}
        <div>
          <p className="block text-sm font-medium text-foreground mb-3">{t('ai.primary')}</p>
          <div className="grid grid-cols-2 gap-4">
            <button
              type="button"
              onClick={() => setAiOverride((prev) => ({ ...prev, provider: 'ollama' }))}
              className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${
                currentAiProvider === 'ollama'
                  ? 'border-brand bg-brand/10'
                  : 'border-border'
              }`}
            >
              <Cpu className="w-6 h-6 text-brand" />
              <div className="text-left">
                <div className="font-medium text-foreground">{t('ai.ollama')}</div>
                <div className="text-xs text-muted-foreground">{t('ai.ollamaDesc')}</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setAiOverride((prev) => ({ ...prev, provider: 'openrouter' }))}
              className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${
                currentAiProvider === 'openrouter'
                  ? 'border-brand bg-brand/10'
                  : 'border-border'
              }`}
            >
              <Cloud className="w-6 h-6 text-brand" />
              <div className="text-left">
                <div className="font-medium text-foreground">{t('ai.openrouter')}</div>
                <div className="text-xs text-muted-foreground">{t('ai.openrouterDesc')}</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setAiOverride((prev) => ({ ...prev, provider: 'lmstudio' }))}
              className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${
                currentAiProvider === 'lmstudio'
                  ? 'border-brand bg-brand/10'
                  : 'border-border'
              }`}
            >
              <Cpu className="w-6 h-6 text-brand" />
              <div className="text-left">
                <div className="font-medium text-foreground">{t('ai.lmstudio')}</div>
                <div className="text-xs text-muted-foreground">{t('ai.localOpenAIAPI')}</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setAiOverride((prev) => ({ ...prev, provider: 'groq' }))}
              className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${
                currentAiProvider === 'groq'
                  ? 'border-brand bg-brand/10'
                  : 'border-border'
              }`}
            >
              <Cloud className="w-6 h-6 text-brand" />
              <div className="text-left">
                <div className="font-medium text-foreground">{t('ai.groq')}</div>
                <div className="text-xs text-muted-foreground">{t('ai.groqDesc')}</div>
              </div>
            </button>
          </div>
        </div>

        <AiProviderFields
          provider={currentAiProvider}
          lmStudioModel={currentLmStudioModel}
          groqModel={currentGroqModel}
          selectedModel={currentSelectedModel}
          openRouterApiKey={currentOpenRouterApiKey}
          groqApiKey={currentGroqApiKey}
          ollamaBaseUrl={currentOllamaBaseUrl}
          lmStudioBaseUrl={currentLmStudioBaseUrl}
          maxTokens={currentMaxTokens}
          temperature={currentTemperature}
          ollamaModels={ollamaModels}
          openRouterModels={openRouterModels}
          lmStudioModels={lmStudioModels}
          groqModels={groqModels}
          loading={loading}
          setAiOverride={setAiOverride}
          modelSearchOpen={modelSearchOpen}
          setModelSearchOpen={setModelSearchOpen}
          modelSearchQuery={modelSearchQuery}
          setModelSearchQuery={setModelSearchQuery}
          onFetchModels={handleFetchModels}
        />
        <div className="flex items-center gap-2 pt-4 border-t border-border">
          <button type="button" onClick={checkHealth} className="px-3 py-2 text-sm text-foreground hover:bg-surface-hover rounded-lg">
            {t('ai.health')}
          </button>
        </div>
        {selectedHealth && (
          <StatusMessage variant={selectedHealth.available ? 'success' : 'error'}>
            <div className="font-medium">
              {selectedProviderLabel}:{' '}
              <span className={selectedHealth.available ? 'text-green-700' : 'text-red-700'}>
                {selectedHealth.available ? t('ai.statusUp') : t('ai.statusDown')}
              </span>
            </div>
            {selectedProviderStatusMessage && (
              <div className="mt-1 text-xs">
                {selectedProviderStatusMessage}
              </div>
            )}
          </StatusMessage>
        )}

        <div className="flex justify-end pt-6 border-t border-border">
          <p className="text-sm text-muted-foreground">
            {t('ai.autoSave')}
          </p>
        </div>
      </div>
    </section>
  );
}
