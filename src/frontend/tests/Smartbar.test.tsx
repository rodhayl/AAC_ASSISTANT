import { act, render, screen, waitFor } from '@testing-library/react';
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
  return {
    useLearningStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>) => {
      if (typeof arg2 === 'string') return arg2;
      const labels: Record<string, string> = {
        more: 'More',
        moreSuggestions: 'More suggestions',
        suggestions: 'Suggestions',
      };
      return labels[key] ?? key;
    },
    i18n: { language: 'en' },
  }),
}));

function word(label: string) {
  return [{ custom_text: label, symbol: { label } }] as never;
}

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Smartbar', () => {
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

describe('Smartbar debounce', () => {
  it('collapses rapid sentence changes into a single prediction fetch', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: [] });

    // Mount with real timers so the initial fetch and act environment settle.
    const { rerender } = render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);
    await waitFor(() => expect(vi.mocked(api.post)).toHaveBeenCalledTimes(1));

    vi.useFakeTimers();
    const callsBefore = vi.mocked(api.post).mock.calls.length;

    // Simulate typing: many rapid sentence updates within the debounce window.
    for (const label of ['h', 'he', 'hel', 'hell', 'hello']) {
      rerender(<Smartbar currentSentence={word(label)} onSelectSymbol={vi.fn()} />);
    }

    // No additional request has fired while the debounce timer is pending.
    expect(vi.mocked(api.post).mock.calls.length).toBe(callsBefore);

    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });

    // Exactly one extra request fired for the final sentence.
    expect(vi.mocked(api.post).mock.calls.length).toBe(callsBefore + 1);
    const lastBody = vi.mocked(api.post).mock.calls.at(-1)?.[1] as { current_symbols: string };
    expect(lastBody.current_symbols).toBe('hello');
  });
});

describe('Smartbar pagination', () => {
  const suggestion = (symbol_id: number, label: string) => ({
    symbol_id,
    label,
    category: 'general',
    confidence: 0.5,
  });

  it('disables the More button when the backend returns a short page', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: [suggestion(1, 'One'), suggestion(2, 'Two'), suggestion(3, 'Three')],
    });

    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    await waitFor(() => {
      const moreButton = screen.getByRole('button', { name: 'More' });
      expect(moreButton).toBeDisabled();
    });
  });

  it('keeps the More button enabled after a full page of suggestions', async () => {
    const fullPage = Array.from({ length: 20 }, (_, index) =>
      suggestion(index + 1, `Word ${index + 1}`),
    );
    vi.mocked(api.post).mockResolvedValue({ data: fullPage });

    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    await waitFor(() => {
      const moreButton = screen.getByRole('button', { name: 'More' });
      expect(moreButton).toBeEnabled();
    });
  });
});

describe('Smartbar request cancellation', () => {
  it('passes an AbortSignal and does not log cancellation as an error', async () => {
    let rejectRequest!: (error: unknown) => void;
    vi.mocked(api.post).mockImplementation(() => new Promise((_resolve, reject) => { rejectRequest = reject; }));
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { unmount } = render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);
    await act(async () => { await Promise.resolve(); });
    expect(vi.mocked(api.post).mock.calls[0][1]).toEqual(expect.objectContaining({}));
    const config = vi.mocked(api.post).mock.calls[0][2];
    expect(config).toEqual(expect.objectContaining({ signal: expect.any(AbortSignal) }));

    unmount();
    await act(async () => { rejectRequest({ code: 'ERR_CANCELED' }); });
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
