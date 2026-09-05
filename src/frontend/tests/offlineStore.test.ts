import { beforeEach, describe, expect, it, vi } from 'vitest';

const readOfflineConflicts = vi.hoisted(() => vi.fn(() => []));
const writeOfflineConflicts = vi.hoisted(() => vi.fn());
const sanitizeOfflineConfig = vi.hoisted(() => vi.fn((config: unknown) => config));
const removeAuthorizationHeader = vi.hoisted(() => vi.fn((config: unknown) => config));
const isPersistableJson = vi.hoisted(() => vi.fn(() => true));

vi.mock('../src/lib/offlinePersistence', () => ({
  readOfflineConflicts,
  writeOfflineConflicts,
  sanitizeOfflineConfig,
  removeAuthorizationHeader,
  isPersistableJson,
}));

import { useOfflineStore, type OfflineConflict } from '../src/store/offlineStore';

function conflict(overrides: Partial<OfflineConflict> = {}): OfflineConflict {
  return {
    id: `c_${Math.random().toString(36).slice(2)}`,
    userId: 7,
    config: { url: '/boards', method: 'post', data: { name: 'x' } },
    error: 'offline',
    timestamp: 1000,
    retryCount: 0,
    ...overrides,
  };
}

describe('offlineStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    readOfflineConflicts.mockReturnValue([]);
    isPersistableJson.mockReturnValue(true);
    useOfflineStore.setState({ conflicts: [] });
  });

  it('skips the dedup check when the payload is not persistable', () => {
    isPersistableJson.mockReturnValue(false);

    useOfflineStore.getState().addConflict({ url: '/boards', method: 'post' }, 'offline', 7);
    useOfflineStore.getState().addConflict({ url: '/boards', method: 'post' }, 'offline again', 7);

    // Non-persistable payloads bypass dedup but are still queued; the
    // persistence layer filters them out when writing.
    expect(useOfflineStore.getState().conflicts).toHaveLength(2);
  });

  it('does not add a duplicate of an already-queued request', () => {
    useOfflineStore.getState().addConflict({ url: '/boards/1', method: 'post' }, 'offline', 7);
    useOfflineStore.getState().addConflict({ url: '/boards/1', method: 'post' }, 'offline again', 7);

    expect(useOfflineStore.getState().conflicts).toHaveLength(1);
  });

  it('discards conflicts that do not belong to the current user', () => {
    useOfflineStore.setState({
      conflicts: [conflict({ id: 'mine' }), conflict({ id: 'foreign', userId: 99 })],
    });

    useOfflineStore.getState().discardForeignConflicts(7);

    expect(useOfflineStore.getState().conflicts.map((c) => c.id)).toEqual(['mine']);
    expect(writeOfflineConflicts).toHaveBeenCalled();
  });

  it('removes a single conflict and persists the list', () => {
    useOfflineStore.setState({
      conflicts: [conflict({ id: 'drop-me' }), conflict({ id: 'keep-me' })],
    });

    useOfflineStore.getState().removeConflict('drop-me');

    expect(useOfflineStore.getState().conflicts.map((c) => c.id)).toEqual(['keep-me']);
    expect(writeOfflineConflicts).toHaveBeenCalled();
  });

  it('falls back to no dedup key when the config cannot be serialized', () => {
    const circular: Record<string, unknown> = { url: '/boards', method: 'post' };
    circular.data = circular;

    useOfflineStore.getState().addConflict(circular as never, 'offline', 7);
    useOfflineStore.getState().addConflict(circular as never, 'offline again', 7);

    // JSON.stringify throws on the circular reference, so no request key is
    // derived and the dedup check is skipped.
    expect(useOfflineStore.getState().conflicts).toHaveLength(2);
  });

  it('increments the retry counter of a single conflict and persists', () => {
    useOfflineStore.setState({ conflicts: [conflict({ id: 'retry-me', retryCount: 2 })] });

    useOfflineStore.getState().incrementRetry('retry-me');

    expect(useOfflineStore.getState().conflicts[0].retryCount).toBe(3);
    expect(writeOfflineConflicts).toHaveBeenCalled();
  });
});
