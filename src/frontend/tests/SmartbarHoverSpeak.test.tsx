import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Smartbar } from '../src/components/board/Smartbar';
import api from '../src/lib/api';

const authState = vi.hoisted(() => ({
  user: {
    settings: {
      hover_speak_enabled: true,
      hover_speak_delay_ms: 1000,
    },
  },
}));

const enqueue = vi.hoisted(() => vi.fn());

vi.mock('../src/lib/api', () => ({
  default: {
    post: vi.fn(),
  },
}));

vi.mock('../src/lib/tts', () => ({
  tts: { enqueue },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
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
    t: (key: string, arg2?: string | Record<string, unknown>) =>
      typeof arg2 === 'string' ? arg2 : key,
    i18n: { language: 'es' },
  }),
}));

describe('Smartbar hover-to-speak', () => {
  beforeEach(() => {
    authState.user.settings.hover_speak_enabled = true;
    authState.user.settings.hover_speak_delay_ms = 1000;
    vi.mocked(api.post).mockResolvedValue({
      data: [
        { symbol_id: 7, label: 'agua', category: 'drinks', confidence: 0.8 },
        { symbol_id: 8, label: ',', category: 'punctuation', confidence: 0.1 },
      ],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('speaks a suggestion after the pointer rests on it for the configured delay', async () => {
    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    const tile = await screen.findByRole('button', { name: /agua/ });

    vi.useFakeTimers();
    fireEvent.mouseEnter(tile);
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(enqueue).not.toHaveBeenCalled();

    // Moving within the tile fires no enter/leave events, so the countdown
    // keeps running and speaks once the delay elapses.
    fireEvent.mouseMove(tile);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(enqueue).toHaveBeenCalledWith('agua', {
      key: 'hover-speak:agua',
      group: 'hover-speak',
    });
  });

  it('does not speak when the pointer leaves before the delay', async () => {
    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    const tile = await screen.findByRole('button', { name: /agua/ });

    vi.useFakeTimers();
    fireEvent.mouseEnter(tile);
    act(() => {
      vi.advanceTimersByTime(500);
    });
    fireEvent.mouseLeave(tile);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(enqueue).not.toHaveBeenCalled();
  });

  it('does not speak punctuation tiles', async () => {
    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    await screen.findByRole('button', { name: /agua/ });
    const punctuation = document.querySelector('button .sr-only')?.closest('button');
    expect(punctuation).not.toBeNull();

    vi.useFakeTimers();
    fireEvent.mouseEnter(punctuation!);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(enqueue).not.toHaveBeenCalled();
  });

  it('stays silent when hover-to-speak is disabled in settings', async () => {
    authState.user.settings.hover_speak_enabled = false;
    render(<Smartbar currentSentence={[]} onSelectSymbol={vi.fn()} />);

    const tile = await screen.findByRole('button', { name: /agua/ });

    vi.useFakeTimers();
    fireEvent.mouseEnter(tile);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(enqueue).not.toHaveBeenCalled();
  });
});
