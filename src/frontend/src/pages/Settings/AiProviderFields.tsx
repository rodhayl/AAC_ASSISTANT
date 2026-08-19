import type { Dispatch, SetStateAction } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { config } from '../../config';
import type { OllamaModel, OpenRouterModel } from '../../store/settingsStore';
import type { AiOverride, AiProvider } from './types';

interface AiProviderFieldsProps {
  provider: AiProvider;
  lmStudioModel: string;
  selectedModel: string;
  openRouterApiKey: string;
  ollamaBaseUrl: string;
  lmStudioBaseUrl: string;
  maxTokens: number;
  temperature: number;
  ollamaModels: OllamaModel[];
  openRouterModels: OpenRouterModel[];
  lmStudioModels: OpenRouterModel[];
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
  selectedModel,
  openRouterApiKey,
  ollamaBaseUrl,
  lmStudioBaseUrl,
  maxTokens,
  temperature,
  ollamaModels,
  openRouterModels,
  lmStudioModels,
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
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('ai.ollamaUrl')}</label>
            <input
              id="primary-ollama-base-url"
              name="primary_ollama_base_url"
              type="text"
              value={ollamaBaseUrl}
              onChange={(event) => setAiOverride((prev) => ({ ...prev, ollama_base_url: event.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              placeholder={config.OLLAMA_BASE_URL}
              aria-label={t('ai.ollamaUrl')}
            />
          </div>
          <div className="relative">
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">{t('ai.models')}</label>
              <button
                type="button"
                onClick={onFetchModels}
                disabled={loading}
                className="flex items-center space-x-1 text-indigo-600 hover:text-indigo-700 text-sm font-medium disabled:opacity-50"
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              aria-label={t('ai.models')}
            />
            {modelSearchOpen && ollamaModels.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
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
                      className="w-full text-left px-4 py-2 hover:bg-indigo-50 transition-colors"
                    >
                      {model.name}
                    </button>
                  ))}
              </div>
            )}
            {selectedModel && !modelSearchQuery && (
              <div className="mt-1 text-sm text-gray-600">{t('ai.selected')} {selectedModel}</div>
            )}
          </div>
        </div>
      )}

      {provider === 'openrouter' && (
        <div className="space-y-4">
          <div>
            <label htmlFor="primary-openrouter-api-key" className="block text-sm font-medium text-gray-700 mb-2">
              {t('ai.apiKey')}
            </label>
            <input
              id="primary-openrouter-api-key"
              name="primary_openrouter_api_key"
              type="password"
              value={openRouterApiKey}
              onChange={(event) =>
                setAiOverride((prev) => ({ ...prev, openrouter_api_key: event.target.value }))
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="sk-or-..."
              aria-label={t('ai.apiKey')}
            />
            <p className="text-xs text-gray-500 mt-1">
              {t('ai.getKey')}{' '}
              <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">
                {t('ai.keysUrl', 'openrouter.ai/keys')}
              </a>
            </p>
          </div>
          <div className="relative">
            <div className="flex items-center justify-between mb-2">
              <label htmlFor="primary-openrouter-model-search" className="block text-sm font-medium text-gray-700">
                {t('ai.models', 'Available Models')}
              </label>
              <button
                type="button"
                onClick={onFetchModels}
                disabled={loading || !openRouterApiKey}
                className="flex items-center space-x-1 text-indigo-600 hover:text-indigo-700 text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>{t('ai.refresh', 'Refresh')}</span>
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              aria-label={t('ai.models')}
            />
            {modelSearchOpen && openRouterModels.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
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
                      className="w-full text-left px-4 py-2 hover:bg-indigo-50 transition-colors"
                    >
                      <div className="font-medium">{model.name}</div>
                      <div className="text-xs text-gray-500">{model.id}</div>
                    </button>
                  ))}
              </div>
            )}
            {selectedModel && !modelSearchQuery && (
              <div className="mt-1 text-sm text-gray-600">{t('ai.selected')} {selectedModel}</div>
            )}
          </div>
        </div>
      )}

      {provider === 'lmstudio' && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('ai.lmstudioUrl', 'LM Studio Base URL')}</label>
            <input
              id="primary-lmstudio-base-url"
              name="primary_lmstudio_base_url"
              type="text"
              value={lmStudioBaseUrl}
              onChange={(event) => setAiOverride((prev) => ({ ...prev, lmstudio_base_url: event.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="http://localhost:1234/v1"
              aria-label={t('ai.lmstudioUrl')}
            />
            <p className="text-xs text-gray-500 mt-1">{t('ai.lmstudioDefault', 'Default: http://localhost:1234/v1')}</p>
          </div>
          <div className="relative">
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">{t('ai.models')}</label>
              <button
                type="button"
                onClick={onFetchModels}
                disabled={loading}
                className="flex items-center space-x-1 text-indigo-600 hover:text-indigo-700 text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>{t('ai.refresh')}</span>
              </button>
            </div>
            <label className="block text-sm font-medium text-gray-700">{t('ai.selectModel', 'Select Model')}</label>
            <select
              id="primary-lmstudio-model"
              name="primary_lmstudio_model"
              value={lmStudioModel}
              onChange={(event) => setAiOverride((prev) => ({ ...prev, lmstudio_model: event.target.value }))}
              className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
              aria-label={t('ai.selectModel')}
            >
              <option value="">{t('ai.selectModelPlaceholder', 'Select a model...')}</option>
              {lmStudioModels.length > 0 ? (
                lmStudioModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.id}
                  </option>
                ))
              ) : (
                <option value="local-model">{t('ai.localModelDefault', 'local-model (Default)')}</option>
              )}
            </select>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <div>
          <label htmlFor="primary-max-tokens" className="block text-sm font-medium text-gray-700 mb-1">
            {t('ai.maxTokens')}
          </label>
          <input
            id="primary-max-tokens"
            name="primary_max_tokens"
            type="number"
            min={64}
            max={4096}
            step={64}
            value={maxTokens}
            onChange={(event) => setAiOverride((prev) => ({ ...prev, max_tokens: Number(event.target.value) || 0 }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            aria-label={t('ai.maxTokens')}
          />
          <div className="mt-1 flex flex-wrap gap-2 text-xs">
            <span className="text-gray-500 mr-1">{t('ai.presets')}</span>
            {[256, 512, 1024].map((value, index) => (
              <button
                key={value}
                type="button"
                onClick={() => setAiOverride((prev) => ({ ...prev, max_tokens: value }))}
                className="px-2 py-1 rounded border border-gray-300 hover:border-indigo-500 hover:text-indigo-600"
              >
                {index === 0 ? t('ai.short') : index === 1 ? t('ai.medium') : t('ai.long')}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-gray-500">{t('ai.maxTokensHelp')}</p>
        </div>
        <div>
          <label htmlFor="primary-temperature" className="block text-sm font-medium text-gray-700 mb-1">
            {t('ai.temperature')}
          </label>
          <input
            id="primary-temperature"
            name="primary_temperature"
            type="number"
            min={0}
            max={1.5}
            step={0.1}
            value={temperature}
            onChange={(event) => setAiOverride((prev) => ({ ...prev, temperature: Number(event.target.value) }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            aria-label={t('ai.temperature')}
          />
          <p className="mt-1 text-xs text-gray-500">{t('ai.temperatureHelp')}</p>
        </div>
      </div>
    </>
  );
}
