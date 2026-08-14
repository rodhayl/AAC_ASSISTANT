import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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
