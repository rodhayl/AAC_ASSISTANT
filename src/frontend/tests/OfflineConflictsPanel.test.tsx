import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OfflineConflictsPanel } from '../src/components/OfflineConflictsPanel';

const retryConflict = vi.hoisted(() => vi.fn());
const isOffline = vi.hoisted(() => vi.fn(() => false));
const storeState = vi.hoisted(() => ({
  conflicts: [
    {
      id: 'conflict-1',
      userId: 7,
      config: { method: 'post', url: '/boards/1' },
      error: 'Network unavailable',
      timestamp: 1,
      retryCount: 0,
    },
  ],
  removeConflict: vi.fn(),
  clearConflicts: vi.fn(),
  incrementRetry: vi.fn(),
  updateConflictError: vi.fn(),
}));
const authState = vi.hoisted(() => ({ user: { id: 7 } }));

vi.mock('../src/store/offlineStore', () => ({
  useOfflineStore: (selector?: (state: typeof storeState) => unknown) =>
    selector ? selector(storeState) : storeState,
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

vi.mock('../src/lib/api', () => ({
  default: { request: vi.fn() },
  apiOffline: {
    isOffline,
    resumeQueue: vi.fn(),
    // Manual retries go through the replay path so an expired token surfaces
    // as a conflict instead of a forced logout (A6).
    retryConflict,
  },
  extractError: (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback,
}));

vi.mock('../src/lib/format', () => ({
  formatTime: () => 'just now',
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        'offline.title': 'Offline Conflicts',
        'offline.clearAll': 'Clear all conflicts',
        'offline.retries': 'Retries',
        'offline.retry': 'Retry',
        'offline.dismiss': 'Dismiss',
        'offline.conflictsHint': 'Hint',
        'offline.retryFailed': 'Retry failed',
      })[key] || key,
  }),
}));

describe('OfflineConflictsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    retryConflict.mockResolvedValue({ data: {} });
    isOffline.mockReturnValue(false);
    authState.user = { id: 7 };
  });

  it('retries a conflict through the replay path and removes it after success', async () => {
    render(<OfflineConflictsPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(storeState.incrementRetry).toHaveBeenCalledWith('conflict-1');
    await waitFor(() => {
      expect(retryConflict).toHaveBeenCalledWith(storeState.conflicts[0].config);
      expect(storeState.removeConflict).toHaveBeenCalledWith('conflict-1');
    });
  });

  it('surfaces a failed retry on the conflict instead of logging only (A6)', async () => {
    retryConflict.mockRejectedValue(new Error('still offline'));
    render(<OfflineConflictsPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(storeState.updateConflictError).toHaveBeenCalledWith(
        'conflict-1',
        'still offline',
      );
    });
    expect(storeState.removeConflict).not.toHaveBeenCalled();
  });

  it('does not replay a conflict belonging to another session (A6)', () => {
    storeState.conflicts[0].userId = 99;
    render(<OfflineConflictsPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(retryConflict).not.toHaveBeenCalled();
    expect(storeState.incrementRetry).not.toHaveBeenCalled();
  });

  it('supports dismissing one conflict and clearing all conflicts', () => {
    render(<OfflineConflictsPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(storeState.removeConflict).toHaveBeenCalledWith('conflict-1');

    fireEvent.click(screen.getByRole('button', { name: 'Clear all conflicts' }));
    expect(storeState.clearConflicts).toHaveBeenCalledWith();
  });
});
