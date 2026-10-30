import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAccessibleInteraction } from '../src/hooks/useAccessibleInteraction';

const authState = vi.hoisted(() => ({
  user: { settings: { dwell_time: 0, ignore_repeats: 0 } },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

function renderHookWith(onClick: (e?: React.MouseEvent) => void) {
  return renderHook(() => useAccessibleInteraction({ onClick }));
}

describe('useAccessibleInteraction', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    authState.user.settings.dwell_time = 0;
    authState.user.settings.ignore_repeats = 0;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fires a normal pointer click when dwell time is disabled', () => {
    const onClick = vi.fn();
    const { result } = renderHookWith(onClick);
    const event = { detail: 1 } as React.MouseEvent;

    act(() => result.current.onClick(event));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('triggers the click after the dwell timeout when enabled', () => {
    authState.user.settings.dwell_time = 500;
    const onClick = vi.fn();
    const { result } = renderHookWith(onClick);
    const event = { detail: 1 } as React.MouseEvent;

    act(() => result.current.onMouseDown(event));
    expect(onClick).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('cancels a pending dwell click when the pointer lifts early', () => {
    authState.user.settings.dwell_time = 500;
    const onClick = vi.fn();
    const { result } = renderHookWith(onClick);
    const event = { detail: 1 } as React.MouseEvent;

    act(() => result.current.onMouseDown(event));
    act(() => result.current.onMouseUp());
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(onClick).not.toHaveBeenCalled();
  });

  it('still allows keyboard activation while dwell is enabled', () => {
    authState.user.settings.dwell_time = 500;
    const onClick = vi.fn();
    const { result } = renderHookWith(onClick);
    const keyboardEvent = { detail: 0 } as React.MouseEvent;

    act(() => result.current.onClick(keyboardEvent));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('debounces repeated clicks within the ignore-repeats window', () => {
    authState.user.settings.ignore_repeats = 500;
    const onClick = vi.fn();
    const { result } = renderHookWith(onClick);
    const event = { detail: 1 } as React.MouseEvent;

    act(() => result.current.onClick(event));
    act(() => result.current.onClick(event));
    expect(onClick).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(600);
    });
    act(() => result.current.onClick(event));
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});
