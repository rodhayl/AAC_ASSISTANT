import { act, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Smartbar } from '../src/components/board/Smartbar';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: { post: vi.fn() },
}));

vi.mock('../src/store/learningStore', () => {
  const state = { messages: [] };
  return {
    useLearningStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key: string, fallback: string) => fallback }),
}));

function word(label: string) {
  return [{ custom_text: label, symbol: { label } }] as never;
}

describe('Smartbar debounce', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

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
