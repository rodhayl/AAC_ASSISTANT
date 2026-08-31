import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useHoverSpeak } from '../src/hooks/useHoverSpeak';

const authState = vi.hoisted(() => ({
  user: {
    settings: {
      hover_speak_enabled: true,
      hover_speak_delay_ms: 1000,
    },
  },
}));

const enqueue = vi.hoisted(() => vi.fn());

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

vi.mock('../src/lib/tts', () => ({
  tts: { enqueue },
}));

describe('useHoverSpeak', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    authState.user.settings.hover_speak_enabled = true;
    authState.user.settings.hover_speak_delay_ms = 1000;
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('returns no handlers when the setting is disabled', () => {
    authState.user.settings.hover_speak_enabled = false;
    const { result } = renderHook(() => useHoverSpeak());

    expect(result.current.hoverSpeakEnabled).toBe(false);
    expect(result.current.getHoverSpeakProps('agua')).toEqual({});
  });

  it('returns no handlers for blank labels', () => {
    const { result } = renderHook(() => useHoverSpeak());

    expect(result.current.getHoverSpeakProps('  ')).toEqual({});
  });

  it('speaks the label after the configured delay', () => {
    const { result } = renderHook(() => useHoverSpeak());
    const props = result.current.getHoverSpeakProps('agua');

    act(() => props.onMouseEnter());
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(enqueue).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(enqueue).toHaveBeenCalledWith('agua', { key: 'hover-speak:agua' });
  });

  it('honors a custom configured delay', () => {
    authState.user.settings.hover_speak_delay_ms = 2500;
    const { result } = renderHook(() => useHoverSpeak());
    const props = result.current.getHoverSpeakProps('hola');

    act(() => props.onMouseEnter());
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(enqueue).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(enqueue).toHaveBeenCalledWith('hola', { key: 'hover-speak:hola' });
  });

  it('cancels the pending utterance when the pointer leaves early', () => {
    const { result } = renderHook(() => useHoverSpeak());
    const props = result.current.getHoverSpeakProps('agua');

    act(() => props.onMouseEnter());
    act(() => {
      vi.advanceTimersByTime(500);
    });
    act(() => props.onMouseLeave());
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(enqueue).not.toHaveBeenCalled();
  });

  it('cancels the pending utterance when the symbol is pressed', () => {
    const { result } = renderHook(() => useHoverSpeak());
    const props = result.current.getHoverSpeakProps('agua');

    act(() => props.onMouseEnter());
    act(() => props.onMouseDown());
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(enqueue).not.toHaveBeenCalled();
  });

  it('does not restart the timer while moving inside the same symbol', () => {
    const { result } = renderHook(() => useHoverSpeak());
    const props = result.current.getHoverSpeakProps('agua');

    // mouseenter fires once per entry; moving within the element emits no
    // further enter/leave events, so the countdown must keep running.
    act(() => props.onMouseEnter());
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(enqueue).toHaveBeenCalledTimes(1);
  });

  it('restarts the countdown when re-entering after leaving', () => {
    const { result } = renderHook(() => useHoverSpeak());
    const props = result.current.getHoverSpeakProps('agua');

    act(() => props.onMouseEnter());
    act(() => {
      vi.advanceTimersByTime(900);
    });
    act(() => props.onMouseLeave());
    act(() => props.onMouseEnter());
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(enqueue).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(enqueue).toHaveBeenCalledTimes(1);
  });

  it('cancels a pending utterance on unmount', () => {
    const { result, unmount } = renderHook(() => useHoverSpeak());
    const props = result.current.getHoverSpeakProps('agua');

    act(() => props.onMouseEnter());
    unmount();
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(enqueue).not.toHaveBeenCalled();
  });
});
