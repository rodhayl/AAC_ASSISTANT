import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OfflineConflictsPanel } from '../src/components/OfflineConflictsPanel';

const request = vi.hoisted(() => vi.fn());
const storeState = vi.hoisted(() => ({
  conflicts: [
    {
      id: 'conflict-1',
      config: { method: 'post', url: '/boards/1' },
      error: 'Network unavailable',
      timestamp: 1,
      retryCount: 0,
    },
  ],
  removeConflict: vi.fn(),
  clearConflicts: vi.fn(),
  incrementRetry: vi.fn(),
}));

vi.mock('../src/store/offlineStore', () => ({
  useOfflineStore: (selector?: (state: typeof storeState) => unknown) =>
    selector ? selector(storeState) : storeState,
}));

vi.mock('../src/lib/api', () => ({
  default: { request },
  apiOffline: { isOffline: () => false, resumeQueue: vi.fn() },
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
      })[key] || key,
  }),
}));

describe('OfflineConflictsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    request.mockResolvedValue({ data: {} });
  });

  it('retries a conflict and removes it after success', async () => {
    render(<OfflineConflictsPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(storeState.incrementRetry).toHaveBeenCalledWith('conflict-1');
    await waitFor(() => {
      expect(request).toHaveBeenCalledWith(storeState.conflicts[0].config);
      expect(storeState.removeConflict).toHaveBeenCalledWith('conflict-1');
    });
  });

  it('supports dismissing one conflict and clearing all conflicts', () => {
    render(<OfflineConflictsPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(storeState.removeConflict).toHaveBeenCalledWith('conflict-1');

    fireEvent.click(screen.getByRole('button', { name: 'Clear all conflicts' }));
    expect(storeState.clearConflicts).toHaveBeenCalledWith();
  });
});
