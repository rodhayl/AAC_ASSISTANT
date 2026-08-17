import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useToastStore } from '../src/store/toastStore';

describe('toast store', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('adds a toast with default type and duration', () => {
    useToastStore.getState().addToast('Hello');

    const [toast] = useToastStore.getState().toasts;
    expect(toast.message).toBe('Hello');
    expect(toast.type).toBe('info');
    expect(toast.duration).toBe(3000);
    expect(toast.id).toBeTruthy();
  });

  it('auto-removes the toast when the duration elapses', () => {
    useToastStore.getState().addToast('Transient', 'success', 500);
    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(499);
    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('does not schedule auto-removal for a zero duration', () => {
    useToastStore.getState().addToast('Sticky', 'warning', 0);

    vi.advanceTimersByTime(10_000);
    expect(useToastStore.getState().toasts).toHaveLength(1);
  });

  it('removes a toast manually by id', () => {
    useToastStore.getState().addToast('First');
    useToastStore.getState().addToast('Second', 'error', 0);
    const [first, second] = useToastStore.getState().toasts;

    useToastStore.getState().removeToast(first.id);

    const remaining = useToastStore.getState().toasts;
    expect(remaining).toHaveLength(1);
    expect(remaining[0].id).toBe(second.id);
  });
});
