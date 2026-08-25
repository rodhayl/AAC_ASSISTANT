import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AiProviderTab } from '../src/pages/Settings/AiProviderTab';

const get = vi.hoisted(() => vi.fn());
const useSettingsStoreMock = vi.hoisted(() => vi.fn());
const settingsState = vi.hoisted(() => ({
  aiSettings: {
    provider: 'ollama' as const,
    ollama_model: 'qwen:7b-q4_0',
    openrouter_model: '',
    lmstudio_model: '',
    groq_model: '',
    openrouter_api_key: '',
    groq_api_key: '',
    ollama_base_url: 'http://localhost:11434',
    lmstudio_base_url: 'http://localhost:1234/v1',
    max_tokens: 1024,
    temperature: 0.5,
    can_edit: true,
  },
  ollamaModels: [],
  openRouterModels: [],
  lmStudioModels: [],
  groqModels: [],
  loading: false,
  error: null as string | null,
  fetchAISettings: vi.fn(),
  updateAISettings: vi.fn(),
  fetchOllamaModels: vi.fn(),
  fetchOpenRouterModels: vi.fn(),
  fetchLmStudioModels: vi.fn(),
  fetchGroqModels: vi.fn(),
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get,
  },
}));

const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'admin1', user_type: 'admin' },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

vi.mock('../src/store/settingsStore', () => ({
  useSettingsStore: useSettingsStoreMock,
}));

vi.mock('../src/pages/Settings/AiProviderFields', () => ({
  AiProviderFields: () => <div data-testid="ai-provider-fields" />,
}));

vi.mock('../src/config', () => ({
  config: {
    OLLAMA_BASE_URL: 'http://localhost:11434',
  },
}));

const tMock = vi.hoisted(() => {
  const table: Record<string, string> = {
    'ai.title': 'AI Provider Configuration',
    'ai.subtitle': 'Configure AI model',
    'ai.primary': 'Primary AI Provider',
    'ai.ollama': 'Ollama',
    'ai.ollamaDesc': 'Local LLM',
    'ai.openrouter': 'OpenRouter',
    'ai.openrouterDesc': 'Cloud API',
    'ai.health': 'Check Provider Health',
  };
  return (key: string, defaultValue?: string | { defaultValue?: string }, options?: Record<string, string>) => {
    if (typeof defaultValue === 'string') {
      let text = defaultValue;
      for (const [name, value] of Object.entries(options || {})) {
        text = text.replace(`{{${name}}}`, value);
      }
      return text;
    }
    return table[key] || key;
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: tMock,
  }),
}));

describe('AiProviderTab', () => {
  beforeEach(() => {
    get.mockReset();
    authState.user = { id: 1, username: 'admin1', user_type: 'admin' };
    useSettingsStoreMock.mockImplementation((selector?: (state: typeof settingsState) => unknown) =>
      selector ? selector(settingsState) : settingsState
    );
  });

  it('shows LM Studio-specific health text when LM Studio is selected', async () => {
    get.mockResolvedValueOnce({
      data: {
        ollama: { available: false, configured: true, reason: null },
        openrouter: { available: false, configured: false, reason: 'api_key_missing' },
        lmstudio: { available: false, configured: true, reason: null },
      },
    });

    render(<AiProviderTab />);

    fireEvent.click(screen.getByText('LM Studio'));
    fireEvent.click(screen.getByText('Check Provider Health'));

    expect(await screen.findByText('LM Studio is not reachable at the configured base URL.')).toBeInTheDocument();
    expect(screen.getByText((content, element) => element?.textContent === 'LM Studio: down')).toBeInTheDocument();
  });

  it('persists provider changes without requiring a second save action', async () => {
    render(<AiProviderTab />);

    fireEvent.click(screen.getByText('OpenRouter'));

    await waitFor(() => {
      expect(settingsState.updateAISettings).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'openrouter',
          ollama_model: 'qwen:7b-q4_0',
        }),
      );
    });
  });

  it('shows OpenRouter API key guidance when OpenRouter is selected without a key', async () => {
    get.mockResolvedValueOnce({
      data: {
        ollama: { available: true, configured: true, reason: null },
        openrouter: { available: false, configured: false, reason: 'api_key_missing' },
        lmstudio: { available: true, configured: true, reason: null },
      },
    });

    render(<AiProviderTab />);

    fireEvent.click(screen.getByText('OpenRouter'));
    fireEvent.click(screen.getByText('Check Provider Health'));

    expect(await screen.findByText('OpenRouter API key is missing.')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText((content, element) => element?.textContent === 'OpenRouter: down')).toBeInTheDocument();
    });
  });

  it('loads read-only settings with one request for non-admin users', async () => {
    authState.user = { id: 2, username: 'student1', user_type: 'student' };
    get.mockResolvedValueOnce({
      data: {
        provider: 'ollama',
        ollama_model: 'student-visible-model',
        openrouter_model: '',
        lmstudio_model: '',
        groq_model: '',
        ollama_base_url: 'http://localhost:11434',
        lmstudio_base_url: 'http://localhost:1234/v1',
        max_tokens: 512,
        temperature: 0.4,
        can_edit: false,
      },
    });

    render(<AiProviderTab />);

    expect(await screen.findByText('student-visible-model')).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith('/settings/ai', expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });
});
