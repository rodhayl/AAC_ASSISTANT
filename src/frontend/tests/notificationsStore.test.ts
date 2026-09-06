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

describe('notifications store read-state and load resilience', () => {
  beforeEach(() => {
    useNotificationsStore.setState({ items: [], loading: false, loaded: false });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    window.dispatchEvent(new Event('aac:auth-logout'));
    vi.restoreAllMocks();
  });

  const item = (id: string | number, read = false) => ({
    id,
    title: `Title ${String(id)}`,
    message: 'Message',
    read,
    createdAt: 0,
  });

  it('syncs numeric ids to the backend and skips sync for local-only ids', async () => {
    const put = vi.spyOn(api, 'put').mockResolvedValue({} as never);

    useNotificationsStore.setState({ items: [item(1)] });
    await useNotificationsStore.getState().markAsRead(1);
    expect(put).toHaveBeenCalledWith('/notifications/1/read');
    expect(useNotificationsStore.getState().items[0].read).toBe(true);

    useNotificationsStore.setState({ items: [item('local-1')] });
    await useNotificationsStore.getState().markAsRead('local-1');
    expect(put).toHaveBeenCalledTimes(1);
    expect(useNotificationsStore.getState().items[0].read).toBe(true);
  });

  it('keeps the local read state when the backend sync fails', async () => {
    vi.spyOn(api, 'put').mockRejectedValue(new Error('offline'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    useNotificationsStore.setState({ items: [item(1)] });
    await useNotificationsStore.getState().markAsRead(1);

    expect(useNotificationsStore.getState().items[0].read).toBe(true);
    expect(consoleSpy).toHaveBeenCalled();
  });

  it('markAllAsRead updates every item and syncs once', async () => {
    const put = vi.spyOn(api, 'put').mockResolvedValue({} as never);
    useNotificationsStore.setState({ items: [item(1), item(2, true), item(3)] });

    await useNotificationsStore.getState().markAllAsRead();

    expect(put).toHaveBeenCalledWith('/notifications/read-all');
    expect(useNotificationsStore.getState().items.every((i) => i.read)).toBe(true);
  });

  it('unreadCount counts only unread items', () => {
    useNotificationsStore.setState({ items: [item(1), item(2, true), item(3)] });
    expect(useNotificationsStore.getState().unreadCount()).toBe(2);
  });

  it('loadFromBackend failure stops loading without crashing', async () => {
    const get = vi.spyOn(api, 'get').mockRejectedValue(new Error('network'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await useNotificationsStore.getState().loadFromBackend(9);

    expect(get).toHaveBeenCalledWith('/notifications', {
      params: { user_id: 9, skip: 0, limit: 100 },
    });
    expect(useNotificationsStore.getState().loading).toBe(false);
    expect(useNotificationsStore.getState().loaded).toBe(false);
    expect(consoleSpy).toHaveBeenCalled();
  });

  it('loadFromBackend walks every page instead of truncating at 50', async () => {
    const firstPage = Array.from({ length: 100 }, (_, i) => ({
      id: i + 1,
      title: `N${i + 1}`,
      message: 'Message',
      is_read: false,
      created_at: '2026-01-01T00:00:00Z',
    }));
    const secondPage = Array.from({ length: 35 }, (_, i) => ({
      id: 101 + i,
      title: `N${101 + i}`,
      message: 'Message',
      is_read: false,
      created_at: '2026-01-02T00:00:00Z',
    }));
    const get = vi.spyOn(api, 'get').mockImplementation((_url: string, config?: { params?: { skip?: number } }) => {
      const skip = config?.params?.skip ?? 0;
      return Promise.resolve({ data: { notifications: skip === 0 ? firstPage : secondPage } });
    });

    await useNotificationsStore.getState().loadFromBackend(1);

    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenNthCalledWith(2, '/notifications', {
      params: { user_id: 1, skip: 100, limit: 100 },
    });
    expect(useNotificationsStore.getState().items).toHaveLength(135);
    expect(useNotificationsStore.getState().loaded).toBe(true);
  });
});
