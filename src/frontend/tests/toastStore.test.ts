import { beforeEach, describe, expect, it, vi } from 'vitest';

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}));

vi.mock('sonner', () => ({ toast }));

import { useToastStore } from '../src/store/toastStore';

describe('toastStore (sonner facade)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps ToastType onto the matching sonner emitter', () => {
    useToastStore.getState().addToast('ok', 'success');
    useToastStore.getState().addToast('bad', 'error');
    useToastStore.getState().addToast('careful', 'warning');
    useToastStore.getState().addToast('fyi');

    expect(toast.success).toHaveBeenCalledWith('ok', { duration: 3000 });
    expect(toast.error).toHaveBeenCalledWith('bad', { duration: 3000 });
    expect(toast.warning).toHaveBeenCalledWith('careful', { duration: 3000 });
    expect(toast.info).toHaveBeenCalledWith('fyi', { duration: 3000 });
  });

  it('passes a custom duration through', () => {
    useToastStore.getState().addToast('slow', 'info', 8000);
    expect(toast.info).toHaveBeenCalledWith('slow', { duration: 8000 });
  });

  it('treats duration 0 as sticky (Infinity, the old sticky contract)', () => {
    useToastStore.getState().addToast('sticky', 'warning', 0);
    expect(toast.warning).toHaveBeenCalledWith('sticky', { duration: Infinity });
  });
});
