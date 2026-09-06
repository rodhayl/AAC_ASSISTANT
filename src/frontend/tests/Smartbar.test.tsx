import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Smartbar } from '../src/components/board/Smartbar';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: {
    post: vi.fn(),
  },
}));

// Hover-to-speak is covered independently; keep these rendering tests
// isolated from the auth/i18n dependencies used by that hook.
vi.mock('../src/hooks/useHoverSpeak', () => ({
  useHoverSpeak: () => ({ getHoverSpeakProps: () => ({}) }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>) => {
      if (typeof arg2 === 'string') return arg2;
      const labels: Record<string, string> = {
        more: 'More',
        moreSuggestions: 'More suggestions',
        previousSuggestions: 'Previous suggestions',
        nextSuggestions: 'Next suggestions',
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
  it('passes the active Learning board ID to the prediction request', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: [] });

    render(
      <Smartbar
        currentSentence={[]}
        onSelectSymbol={vi.fn()}
        boardId={42}
      />,
    );

    await waitFor(() => expect(vi.mocked(api.post)).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.post).mock.calls[0][1]).toEqual(
      expect.objectContaining({ board_id: 42 }),
    );
  });

  it('does not send the dead chat_history payload', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: [] });

    render(
      <Smartbar
        currentSentence={[]}
        onSelectSymbol={vi.fn()}
        boardId={42}
      />,
    );

    await waitFor(() => expect(vi.mocked(api.post)).toHaveBeenCalledTimes(1));
    const body = vi.mocked(api.post).mock.calls[0][1] as Record<string, unknown>;
    expect(body).not.toHaveProperty('chat_history');
  });

  it('passes the active Learning topic to the prediction request', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: [] });

    render(
      <Smartbar
        currentSentence={[]}
        onSelectSymbol={vi.fn()}
        topic="Inteligencia Artificial y LLMs"
      />,
    );

    await waitFor(() => expect(vi.mocked(api.post)).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.post).mock.calls[0][1]).toEqual(
      expect.objectContaining({ topic: 'Inteligencia Artificial y LLMs' }),
    );
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

  it('renders LLM text-only topic words and selects them as custom text', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: [
        {
          symbol_id: -123,
          label: 'nebulosa',
          category: null,
          image_path: null,
          confidence: 0.7,
          source: 'ai',
          is_text_only: true,
        },
      ],
    });
    const onSelect = vi.fn();

    render(<Smartbar currentSentence={[]} onSelectSymbol={onSelect} />);

    await waitFor(() => {
      expect(screen.getByText('nebulosa')).toBeInTheDocument();
    });

    // Text-only words carry no image; the letter tile substitutes.
    expect(screen.getByText('n')).toBeInTheDocument();

    fireEvent.click(screen.getByText('nebulosa'));
    const selected = onSelect.mock.calls[0][0];
    expect(selected.custom_text).toBe('nebulosa');
    expect(selected.symbol_id).toBe(-123);
    expect(selected.symbol.image_path).toBeNull();
  });

  it('shows a generating state on text-only words awaiting a pictogram', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: [
        {
          symbol_id: -1,
          label: 'quasar',
          category: null,
          image_path: null,
          confidence: 0.7,
          source: 'ai',
          is_text_only: true,
          is_generating: true,
        },
      ],
    });

    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('quasar')).toBeInTheDocument();
    });
    expect(screen.getByTestId('smartbar-generating-tile')).toBeInTheDocument();
  });

  it('auto-refreshes and upgrades the tile once the pictogram exists', async () => {
    vi.useFakeTimers();
    const onSelect = vi.fn();
    const pending = {
      symbol_id: -2,
      label: 'singulares',
      category: null,
      image_path: null,
      confidence: 0.7,
      source: 'ai',
      is_text_only: true,
      is_generating: true,
    };
    const upgraded = {
      symbol_id: 502,
      label: 'singulares',
      category: 'space',
      image_path: '/uploads/symbols/x.png',
      confidence: 0.7,
      source: 'ai',
    };
    const postMock = vi.mocked(api.post);
    postMock.mockResolvedValueOnce({ data: [pending] }).mockResolvedValueOnce({ data: [upgraded] });

    render(<Smartbar currentSentence={[]} onSelectSymbol={onSelect} />);

    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('smartbar-generating-tile')).toBeInTheDocument();
    expect(postMock).toHaveBeenCalledTimes(1);

    // Let the auto-refresh timer fire: the tile upgrades to the real image
    // and the spinner disappears.
    await act(async () => {
      vi.advanceTimersByTime(4000);
    });
    await act(async () => { await Promise.resolve(); });

    expect(postMock).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId('smartbar-generating-tile')).not.toBeInTheDocument();
    const image = screen.getByAltText('singulares');
    expect(image).toHaveAttribute('src', '/uploads/symbols/x.png');
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

  it('shows accessible controls and scrolls the suggestions row horizontally', async () => {
    const fullPage = Array.from({ length: 20 }, (_, index) =>
      suggestion(index + 1, `Word ${index + 1}`),
    );
    vi.mocked(api.post).mockResolvedValue({ data: fullPage });

    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);
    const container = await screen.findByTestId('smartbar-suggestions');
    Object.defineProperties(container, {
      clientWidth: { configurable: true, value: 320 },
      scrollWidth: { configurable: true, value: 640 },
      scrollLeft: { configurable: true, writable: true, value: 0 },
    });
    const scrollBy = vi.fn();
    Object.defineProperty(container, 'scrollBy', { configurable: true, value: scrollBy });

    await act(async () => {
      window.dispatchEvent(new Event('resize'));
    });

    const nextButton = await screen.findByRole('button', { name: 'Next suggestions' });
    expect(nextButton).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Previous suggestions' })).toBeDisabled();
    expect(screen.getByTestId('smartbar-right-overflow-indicator')).toBeInTheDocument();
    expect(screen.queryByTestId('smartbar-left-overflow-indicator')).not.toBeInTheDocument();

    fireEvent.click(nextButton);
    expect(scrollBy).toHaveBeenCalledWith({ left: 256, behavior: 'smooth' });

    container.scrollLeft = 320;
    fireEvent.scroll(container);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Previous suggestions' })).toBeEnabled();
      expect(screen.getByTestId('smartbar-left-overflow-indicator')).toBeInTheDocument();
      expect(screen.queryByTestId('smartbar-right-overflow-indicator')).not.toBeInTheDocument();
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
