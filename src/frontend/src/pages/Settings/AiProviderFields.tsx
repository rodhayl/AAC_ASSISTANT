import type { Dispatch, SetStateAction } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { config } from '../../config';
import type { OllamaModel, OpenRouterModel } from '../../store/settingsStore';
import type { AiOverride, AiProvider } from './types';

import { FormLabel } from '@/components/ui/FormLabel';
interface AiProviderFieldsProps {
  provider: AiProvider;
  lmStudioModel: string;
  groqModel: string;
  selectedModel: string;
  openRouterApiKey: string;
  groqApiKey: string;
  ollamaBaseUrl: string;
  lmStudioBaseUrl: string;
  maxTokens: number;
  temperature: number;
  autogenDailyCap: number;
  ollamaModels: OllamaModel[];
  openRouterModels: OpenRouterModel[];
  lmStudioModels: OpenRouterModel[];
  groqModels: OpenRouterModel[];
  loading: boolean;
  setAiOverride: Dispatch<SetStateAction<AiOverride>>;
  modelSearchOpen: boolean;
  setModelSearchOpen: (open: boolean) => void;
  modelSearchQuery: string;
  setModelSearchQuery: (query: string) => void;
  onFetchModels: () => Promise<void>;
}

export function AiProviderFields({
  provider,
  lmStudioModel,
  groqModel,
  selectedModel,
  openRouterApiKey,
  groqApiKey,
  ollamaBaseUrl,
  lmStudioBaseUrl,
  maxTokens,
  temperature,
  autogenDailyCap,
  ollamaModels,
  openRouterModels,
  lmStudioModels,
  groqModels,
  loading,
  setAiOverride,
  modelSearchOpen,
  setModelSearchOpen,
  modelSearchQuery,
  setModelSearchQuery,
  onFetchModels,
}: AiProviderFieldsProps) {
  const { t } = useTranslation('settings');

  return (
    <>
      {provider === 'ollama' && (
        <div className="space-y-4">
          <div>
            <FormLabel className="mb-2">{t('ai.ollamaUrl')}</FormLabel>
            <input
              id="primary-ollama-base-url"
              name="primary_ollama_base_url"
              type="text"
              value={ollamaBaseUrl}
              onChange={(event) => setAiOverride((prev) => ({ ...prev, ollama_base_url: event.target.value }))}
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
              placeholder={config.OLLAMA_BASE_URL}
              aria-label={t('ai.ollamaUrl')}
            />
          </div>
          <div className="relative">
            <div className="flex items-center justify-between mb-2">
              <FormLabel>{t('ai.models')}</FormLabel>
              <button
                type="button"
                onClick={onFetchModels}
                disabled={loading}
                className="flex items-center space-x-1 text-brand hover:text-brand text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>{t('ai.refresh')}</span>
              </button>
            </div>
            <input
              id="primary-ollama-model-search"
              name="primary_ollama_model_search"
              type="text"
              value={modelSearchQuery || selectedModel}
              onChange={(event) => {
                setModelSearchQuery(event.target.value);
                setModelSearchOpen(true);
              }}
              onKeyDown={(event) => {
                if (event.key !== 'Enter') return;
                const model = ollamaModels.find((candidate) => candidate.name === modelSearchQuery.trim());
                if (model) {
                  setAiOverride((prev) => ({ ...prev, ollama_model: model.name }));
                  setModelSearchQuery('');
                  setModelSearchOpen(false);
                }
              }}
              onFocus={() => setModelSearchOpen(true)}
              placeholder={t('ai.searchModels')}
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
              aria-label={t('ai.models')}
            />
            {modelSearchOpen && ollamaModels.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-surface border border-border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                {ollamaModels
                  .filter((model) => model.name.toLowerCase().includes(modelSearchQuery.toLowerCase()))
                  .map((model) => (
                    <button
                      type="button"
                      key={model.name}
                      onClick={() => {
                        setAiOverride((prev) => ({ ...prev, ollama_model: model.name }));
                        setModelSearchQuery('');
                        setModelSearchOpen(false);
                      }}
                      className="w-full text-left px-4 py-2 hover:bg-brand/10  transition-colors"
                    >
                      {model.name}
                    </button>
                  ))}
              </div>
            )}
            {selectedModel && !modelSearchQuery && (
              <div className="mt-1 text-sm text-muted-foreground">{t('ai.selected')} {selectedModel}</div>
            )}
          </div>
        </div>
      )}

      {provider === 'openrouter' && (
        <div className="space-y-4">
          <div>
            <FormLabel htmlFor="primary-openrouter-api-key" className="mb-2">
              {t('ai.apiKey')}
            </FormLabel>
            <input
              id="primary-openrouter-api-key"
              name="primary_openrouter_api_key"
              type="password"
              value={openRouterApiKey}
              onChange={(event) =>
                setAiOverride((prev) => ({ ...prev, openrouter_api_key: event.target.value }))
              }
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
              placeholder="sk-or-..."
              aria-label={t('ai.apiKey')}
            />
            <p className="text-xs text-muted-foreground mt-1">
              {t('ai.getKey')}{' '}
              <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">
                {t('ai.keysUrl')}
              </a>
            </p>
          </div>
          <div className="relative">
            <div className="flex items-center justify-between mb-2">
              <FormLabel htmlFor="primary-openrouter-model-search">
                {t('ai.models')}
              </FormLabel>
              <button
                type="button"
                onClick={onFetchModels}
                disabled={loading || !openRouterApiKey}
                className="flex items-center space-x-1 text-brand hover:text-brand text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>{t('ai.refresh')}</span>
              </button>
            </div>
            <input
              id="primary-openrouter-model-search"
              name="primary_openrouter_model_search"
              type="text"
              value={modelSearchQuery || selectedModel}
              onChange={(event) => {
                setModelSearchQuery(event.target.value);
                setModelSearchOpen(true);
              }}
              onKeyDown={(event) => {
                if (event.key !== 'Enter') return;
                const model = openRouterModels.find((candidate) => candidate.id === modelSearchQuery.trim());
                if (model) {
                  setAiOverride((prev) => ({ ...prev, openrouter_model: model.id }));
                  setModelSearchQuery('');
                  setModelSearchOpen(false);
                }
              }}
              onFocus={() => setModelSearchOpen(true)}
              placeholder={t('ai.searchModels')}
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
              aria-label={t('ai.models')}
            />
            {modelSearchOpen && openRouterModels.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-surface border border-border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                {openRouterModels
                  .filter(
                    (model) =>
                      model.name.toLowerCase().includes(modelSearchQuery.toLowerCase()) ||
                      model.id.toLowerCase().includes(modelSearchQuery.toLowerCase()),
                  )
                  .map((model) => (
                    <button
                      type="button"
                      key={model.id}
                      onClick={() => {
                        setAiOverride((prev) => ({ ...prev, openrouter_model: model.id }));
                        setModelSearchQuery('');
                        setModelSearchOpen(false);
                      }}
                      className="w-full text-left px-4 py-2 hover:bg-brand/10  transition-colors"
                    >
                      <div className="font-medium">{model.name}</div>
                      <div className="text-xs text-muted-foreground">{model.id}</div>
                    </button>
                  ))}
              </div>
            )}
            {selectedModel && !modelSearchQuery && (
              <div className="mt-1 text-sm text-muted-foreground">{t('ai.selected')} {selectedModel}</div>
            )}
          </div>
        </div>
      )}

      {provider === 'groq' && (
        <div className="space-y-4">
          <div>
            <FormLabel htmlFor="primary-groq-api-key" className="mb-2">
              {t('ai.groqApiKey')}
            </FormLabel>
            <input
              id="primary-groq-api-key"
              name="primary_groq_api_key"
              type="password"
              value={groqApiKey}
              onChange={(event) =>
                setAiOverride((prev) => ({ ...prev, groq_api_key: event.target.value }))
              }
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
              placeholder="gsk_..."
              aria-label={t('ai.groqApiKey')}
            />
            <p className="text-xs text-muted-foreground mt-1">
              {t('ai.getKey')}{' '}
              <a href="https://console.groq.com/keys" target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">
                {t('ai.groqKeysUrl')}
              </a>
            </p>
          </div>
          <div className="relative">
            <div className="flex items-center justify-between mb-2">
              <FormLabel htmlFor="primary-groq-model-search">
                {t('ai.models')}
              </FormLabel>
              <button
                type="button"
                onClick={onFetchModels}
                disabled={loading || !groqApiKey}
                className="flex items-center space-x-1 text-brand hover:text-brand text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>{t('ai.refresh')}</span>
              </button>
            </div>
            <input
              id="primary-groq-model-search"
              name="primary_groq_model_search"
              type="text"
              value={modelSearchQuery || groqModel}
              onChange={(event) => {
                setModelSearchQuery(event.target.value);
                setModelSearchOpen(true);
              }}
              onKeyDown={(event) => {
                if (event.key !== 'Enter') return;
                const model = groqModels.find((candidate) => candidate.id === modelSearchQuery.trim());
                if (model) {
                  setAiOverride((prev) => ({ ...prev, groq_model: model.id }));
                  setModelSearchQuery('');
                  setModelSearchOpen(false);
                }
              }}
              onFocus={() => setModelSearchOpen(true)}
              placeholder={t('ai.searchModels')}
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
              aria-label={t('ai.models')}
            />
            {modelSearchOpen && groqModels.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-surface border border-border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                {groqModels
                  .filter(
                    (model) =>
                      model.name.toLowerCase().includes(modelSearchQuery.toLowerCase()) ||
                      model.id.toLowerCase().includes(modelSearchQuery.toLowerCase()),
                  )
                  .map((model) => (
                    <button
                      type="button"
                      key={model.id}
                      onClick={() => {
                        setAiOverride((prev) => ({ ...prev, groq_model: model.id }));
                        setModelSearchQuery('');
                        setModelSearchOpen(false);
                      }}
                      className="w-full text-left px-4 py-2 hover:bg-brand/10  transition-colors"
                    >
                      <div className="font-medium">{model.name}</div>
                      <div className="text-xs text-muted-foreground">{model.id}</div>
                    </button>
                  ))}
              </div>
            )}
            {groqModel && !modelSearchQuery && (
              <div className="mt-1 text-sm text-muted-foreground">{t('ai.selected')} {groqModel}</div>
            )}
          </div>
        </div>
      )}

      {provider === 'lmstudio' && (
        <div className="space-y-4">
          <div>
            <FormLabel className="mb-2">{t('ai.lmstudioUrl')}</FormLabel>
            <input
              id="primary-lmstudio-base-url"
              name="primary_lmstudio_base_url"
              type="text"
              value={lmStudioBaseUrl}
              onChange={(event) => setAiOverride((prev) => ({ ...prev, lmstudio_base_url: event.target.value }))}
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
              placeholder={config.LMSTUDIO_BASE_URL}
              aria-label={t('ai.lmstudioUrl')}
            />
            <p className="text-xs text-muted-foreground mt-1">{t('ai.lmstudioDefault', { url: config.LMSTUDIO_BASE_URL })}</p>
          </div>
          <div className="relative">
            <div className="flex items-center justify-between mb-2">
              <FormLabel>{t('ai.models')}</FormLabel>
              <button
                type="button"
                onClick={onFetchModels}
                disabled={loading}
                className="flex items-center space-x-1 text-brand hover:text-brand text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>{t('ai.refresh')}</span>
              </button>
            </div>
            <FormLabel>{t('ai.selectModel')}</FormLabel>
            <select
              id="primary-lmstudio-model"
              name="primary_lmstudio_model"
              value={lmStudioModel}
              onChange={(event) => setAiOverride((prev) => ({ ...prev, lmstudio_model: event.target.value }))}
              className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border focus:outline-none focus:ring-brand focus:border-brand sm:text-sm rounded-md"
              aria-label={t('ai.selectModel')}
            >
              <option value="">{t('ai.selectModelPlaceholder')}</option>
              {lmStudioModels.length > 0 ? (
                lmStudioModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.id}
                  </option>
                ))
              ) : (
                <option value="local-model">{t('ai.localModelDefault')}</option>
              )}
            </select>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <div>
          <FormLabel htmlFor="primary-max-tokens">
            {t('ai.maxTokens')}
          </FormLabel>
          <input
            id="primary-max-tokens"
            name="primary_max_tokens"
            type="number"
            min={64}
            max={4096}
            step={64}
            value={maxTokens}
            onChange={(event) => setAiOverride((prev) => ({ ...prev, max_tokens: Number(event.target.value) || 0 }))}
            className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand text-sm"
            aria-label={t('ai.maxTokens')}
          />
          <div className="mt-1 flex flex-wrap gap-2 text-xs">
            <span className="text-muted-foreground mr-1">{t('ai.presets')}</span>
            {[256, 512, 1024].map((value, index) => (
              <button
                key={value}
                type="button"
                onClick={() => setAiOverride((prev) => ({ ...prev, max_tokens: value }))}
                className="px-2 py-1 rounded border border-border hover:border-brand hover:text-brand hover:border-brand hover:text-brand"
              >
                {index === 0 ? t('ai.short') : index === 1 ? t('ai.medium') : t('ai.long')}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t('ai.maxTokensHelp')}</p>
        </div>
        <div>
          <FormLabel htmlFor="primary-temperature">
            {t('ai.temperature')}
          </FormLabel>
          <input
            id="primary-temperature"
            name="primary_temperature"
            type="number"
            min={0}
            max={1.5}
            step={0.1}
            value={temperature}
            onChange={(event) => setAiOverride((prev) => ({ ...prev, temperature: Number(event.target.value) }))}
            className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand text-sm"
            aria-label={t('ai.temperature')}
          />
          <p className="mt-1 text-xs text-muted-foreground">{t('ai.temperatureHelp')}</p>
        </div>
        <div>
          <FormLabel htmlFor="primary-autogen-daily-cap">
            {t('ai.autogenDailyCap')}
          </FormLabel>
          <input
            id="primary-autogen-daily-cap"
            name="primary_autogen_daily_cap"
            type="number"
            min={0}
            max={500}
            step={1}
            value={autogenDailyCap}
            onChange={(event) =>
              setAiOverride((prev) => ({ ...prev, autogen_daily_cap: Number(event.target.value) }))
            }
            className="w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand text-sm"
            aria-label={t('ai.autogenDailyCap')}
          />
          <p className="mt-1 text-xs text-muted-foreground">{t('ai.autogenDailyCapHelp')}</p>
        </div>
      </div>
    </>
  );
}
