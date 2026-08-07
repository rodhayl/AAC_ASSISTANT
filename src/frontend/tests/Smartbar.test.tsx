import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Smartbar } from '../src/components/board/Smartbar';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: {
    post: vi.fn(),
  },
}));

vi.mock('../src/store/learningStore', () => {
  const state = { messages: [] };
  const useLearningStore = (selector?: (value: typeof state) => unknown) =>
    selector ? selector(state) : state;
  return { useLearningStore };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
  }),
}));

describe('Smartbar', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders repeated suggestion ids without duplicate React key warnings', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: [
        {
          symbol_id: 13,
          label: 'First label',
          category: 'general',
          confidence: 0.8,
        },
        {
          symbol_id: 13,
          label: 'Second label',
          category: 'general',
          confidence: 0.7,
        },
        {
          symbol_id: 14,
          label: 'Third label',
          category: 'general',
          confidence: 0.6,
        },
        {
          symbol_id: 14,
          label: 'Fourth label',
          category: 'general',
          confidence: 0.5,
        },
      ],
    });
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('First label')).toBeInTheDocument();
      expect(screen.getByText('Second label')).toBeInTheDocument();
      expect(screen.getByText('Third label')).toBeInTheDocument();
      expect(screen.getByText('Fourth label')).toBeInTheDocument();
    });

    const loggedArguments = consoleError.mock.calls.flat().join(' ');
    expect(loggedArguments).not.toContain('same key');
  });
});
