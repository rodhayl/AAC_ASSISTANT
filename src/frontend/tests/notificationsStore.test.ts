import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../src/lib/api';
import { useNotificationsStore } from '../src/store/notificationsStore';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe('notifications store session isolation', () => {
  beforeEach(() => {
    useNotificationsStore.setState({ items: [], loading: false, loaded: false });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    window.dispatchEvent(new Event('aac:auth-logout'));
    vi.restoreAllMocks();
  });

  it('reloads notifications after an auth context change', async () => {
    const get = vi.spyOn(api, 'get')
      .mockResolvedValueOnce({
        data: { notifications: [{ id: 1, title: 'A', message: 'A', is_read: false, created_at: '2026-01-01T00:00:00Z' }] },
      } as never)
      .mockResolvedValueOnce({
        data: { notifications: [{ id: 2, title: 'B', message: 'B', is_read: false, created_at: '2026-01-02T00:00:00Z' }] },
      } as never);

    await useNotificationsStore.getState().loadFromBackend(1);
    expect(useNotificationsStore.getState().items[0].id).toBe(1);

    window.dispatchEvent(new Event('aac:auth-context-changed'));
    await useNotificationsStore.getState().loadFromBackend(2);

    expect(get).toHaveBeenCalledTimes(2);
    expect(useNotificationsStore.getState().items[0].id).toBe(2);
  });

  it('ignores an old response after the auth context changes', async () => {
    const first = deferred<{ data: { notifications: Array<{ id: number; title: string; message: string; is_read: boolean; created_at: string }> } }>();
    const second = deferred<{ data: { notifications: Array<{ id: number; title: string; message: string; is_read: boolean; created_at: string }> } }>();
    vi.spyOn(api, 'get')
      .mockReturnValueOnce(first.promise as never)
      .mockReturnValueOnce(second.promise as never);

    const firstLoad = useNotificationsStore.getState().loadFromBackend(1);
    window.dispatchEvent(new Event('aac:auth-context-changed'));
    const secondLoad = useNotificationsStore.getState().loadFromBackend(2);

    second.resolve({
      data: { notifications: [{ id: 2, title: 'B', message: 'B', is_read: false, created_at: '2026-01-02T00:00:00Z' }] },
    });
    await secondLoad;

    first.resolve({
      data: { notifications: [{ id: 1, title: 'A', message: 'A', is_read: false, created_at: '2026-01-01T00:00:00Z' }] },
    });
    await firstLoad;

    expect(useNotificationsStore.getState().items[0].id).toBe(2);
  });
});
