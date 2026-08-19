import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AiProviderFields } from '../src/pages/Settings/AiProviderFields';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => {
      const table: Record<string, string> = {
        'ai.ollamaUrl': 'Ollama Base URL',
        'ai.models': 'Available Models',
        'ai.apiKey': 'OpenRouter API Key',
        'ai.lmstudioUrl': 'LM Studio Base URL',
        'ai.selectModel': 'Select Model',
        'ai.maxTokens': 'Max tokens per reply',
        'ai.temperature': 'Temperature',
        'ai.refresh': 'Refresh',
        'ai.searchModels': 'Search models...',
        'ai.selected': 'Selected:',
      };
      return table[key] ?? defaultValue ?? key;
    },
  }),
}));

vi.mock('../src/config', () => ({
  config: { OLLAMA_BASE_URL: 'http://localhost:11434' },
}));

const baseProps = {
  lmStudioModel: '',
  selectedModel: '',
  openRouterApiKey: '',
  ollamaBaseUrl: 'http://localhost:11434',
  lmStudioBaseUrl: 'http://localhost:1234/v1',
  maxTokens: 1024,
  temperature: 0.5,
  ollamaModels: [] as Array<{ name: string }>,
  openRouterModels: [] as Array<{ id: string; name: string }>,
  lmStudioModels: [] as Array<{ id: string; name: string }>,
  loading: false,
  setAiOverride: vi.fn(),
  modelSearchOpen: false,
  setModelSearchOpen: vi.fn(),
  modelSearchQuery: '',
  setModelSearchQuery: vi.fn(),
  onFetchModels: vi.fn(),
};

describe('AiProviderFields', () => {
  it('uses localized accessible labels on the Ollama fields', () => {
    render(<AiProviderFields {...baseProps} provider="ollama" />);

    expect(screen.getByLabelText('Ollama Base URL')).toBeInTheDocument();
    // The model search field reuses the "Available Models" label.
    expect(screen.getByLabelText('Available Models')).toBeInTheDocument();
  });

  it('uses localized accessible labels on the OpenRouter fields', () => {
    render(<AiProviderFields {...baseProps} provider="openrouter" />);

    expect(screen.getByLabelText('OpenRouter API Key')).toBeInTheDocument();
    expect(screen.getByLabelText('Available Models')).toBeInTheDocument();
  });

  it('uses localized accessible labels on the LM Studio and common fields', () => {
    render(<AiProviderFields {...baseProps} provider="lmstudio" />);

    expect(screen.getByLabelText('LM Studio Base URL')).toBeInTheDocument();
    expect(screen.getByLabelText('Select Model')).toBeInTheDocument();
    expect(screen.getByLabelText('Max tokens per reply')).toBeInTheDocument();
    expect(screen.getByLabelText('Temperature')).toBeInTheDocument();
  });
});
