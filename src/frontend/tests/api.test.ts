import { afterEach, describe, expect, it, vi } from 'vitest';
import api, { extractError, isAuthFlowEndpoint } from '../src/lib/api';
import { useAuthStore } from '../src/store/authStore';
import { useOfflineStore } from '../src/store/offlineStore';

describe('auth response handling', () => {
  afterEach(() => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('aac:auth-logout'));
      window.dispatchEvent(new Event('online'));
    }
    useOfflineStore.getState().clearConflicts();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('preserves supported backend error payload shapes', () => {
    expect(extractError({ response: { data: { detail: 'detail' } } }, 'fallback')).toBe('detail');
    expect(extractError({ response: { data: { error: 'error' } } }, 'fallback')).toBe('error');
    expect(extractError({ response: { data: { message: 'message' } } }, 'fallback')).toBe('message');
    expect(extractError({ message: 'client error' }, 'fallback')).toBe('client error');
  });

  it('recognizes auth endpoints whose 401 responses belong to the active flow', () => {
    expect(isAuthFlowEndpoint('/auth/token')).toBe(true);
    expect(isAuthFlowEndpoint('/api/auth/refresh?refresh_token=token')).toBe(true);
    expect(isAuthFlowEndpoint('https://localhost/api/auth/change-password')).toBe(true);
    expect(isAuthFlowEndpoint('/auth/tokenize')).toBe(false);
    expect(isAuthFlowEndpoint('/boards/1')).toBe(false);
  });

  it.each([
    ['Authorization', 'Bearer fresh-token'],
    ['authorization', 'Bearer lowercase-token'],
  ])('preserves an explicitly supplied %s header over the stored token', async (headerName, expected) => {
    useAuthStore.setState({ token: 'stale-token' });
    let requestAuthorization: unknown;

    await api.request({
      url: '/auth/users/8',
      method: 'get',
      headers: { [headerName]: expected },
      adapter: (config) => {
        requestAuthorization = config.headers?.Authorization ?? config.headers?.authorization;
        return Promise.resolve({
          data: {},
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        });
      },
    });

    expect(requestAuthorization).toBe(expected);
  });

  it('does not log out for an auth-flow 401', async () => {
    const logout = vi.fn();
    const state = useAuthStore.getState();
    vi.spyOn(useAuthStore, 'getState').mockReturnValue({ ...state, logout });

    await expect(api.request({
      url: '/auth/token',
      method: 'post',
      adapter: (config) => Promise.reject({
        config,
        response: { status: 401 },
      }),
    })).rejects.toMatchObject({ response: { status: 401 } });

    expect(logout).not.toHaveBeenCalled();
  });

  it('keeps logging out for a non-auth 401', async () => {
    const logout = vi.fn();
    const state = useAuthStore.getState();
    vi.spyOn(useAuthStore, 'getState').mockReturnValue({ ...state, logout });
    vi.stubGlobal('window', undefined);

    await expect(api.request({
      url: '/boards/1',
      method: 'get',
      adapter: (config) => Promise.reject({
        config,
        response: { status: 401 },
      }),
    })).rejects.toMatchObject({ response: { status: 401 } });

    expect(logout).toHaveBeenCalledOnce();
  });

  it('drops offline mutations when the session logs out before reconnecting', async () => {
    const adapter = vi.fn().mockResolvedValue({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    });

    window.dispatchEvent(new Event('offline'));
    await expect(api.request({
      url: '/boards/1',
      method: 'post',
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

    useOfflineStore.getState().addConflict({ url: '/boards/1', method: 'post' }, 'stale');
    expect(useOfflineStore.getState().conflicts).toHaveLength(1);

    useAuthStore.getState().logout();
    expect(useOfflineStore.getState().conflicts).toHaveLength(0);

    window.dispatchEvent(new Event('online'));
    await Promise.resolve();
    expect(adapter).not.toHaveBeenCalled();
  });

  it('bounds queued offline mutations', async () => {
    const adapter = vi.fn();
    window.dispatchEvent(new Event('offline'));

    for (let index = 0; index < 100; index += 1) {
      await expect(api.request({
        url: `/boards/${index}`,
        method: 'post',
        adapter,
      })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });
    }

    await expect(api.request({
      url: '/boards/overflow',
      method: 'post',
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE_QUEUE_FULL' });
    expect(useOfflineStore.getState().conflicts).toHaveLength(1);
    expect(useOfflineStore.getState().conflicts[0].error).toBe('Offline mutation queue is full');
    useOfflineStore.getState().addConflict({ url: '/boards/overflow', method: 'post' }, 'still full');
    expect(useOfflineStore.getState().conflicts).toHaveLength(1);
    expect(adapter).not.toHaveBeenCalled();
  });

  it('replays offline mutations in FIFO order without a concurrent burst', async () => {
    let resolveFirst: (() => void) | undefined;
    const secondAdapter = vi.fn();
    const adapter = vi.fn().mockImplementation((config) => {
      if (config.url === '/boards/first') {
        return new Promise((resolve) => {
          resolveFirst = () => resolve({
            data: {},
            status: 200,
            statusText: 'OK',
            headers: {},
            config,
          });
        });
      }
      return Promise.resolve({
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      });
    });

    window.dispatchEvent(new Event('offline'));
    await expect(api.request({ url: '/boards/first', method: 'post', adapter })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });
    await expect(api.request({ url: '/boards/second', method: 'post', adapter: secondAdapter })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

    window.dispatchEvent(new Event('online'));
    await vi.waitFor(() => expect(adapter).toHaveBeenCalledOnce());
    expect(secondAdapter).not.toHaveBeenCalled();

    resolveFirst?.();
    await vi.waitFor(() => expect(secondAdapter).toHaveBeenCalledOnce());
  });

  it('does not queue auth mutations while offline', async () => {
    const adapter = vi.fn().mockResolvedValue({
      data: { access_token: 'fresh-token' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    });

    window.dispatchEvent(new Event('offline'));
    await api.request({
      url: '/auth/refresh',
      method: 'post',
      adapter,
    });

    expect(adapter).toHaveBeenCalledOnce();
  });

  it('aborts a replay already started when the session logs out', async () => {
    let replaySignal: AbortSignal | undefined;
    const adapter = vi.fn().mockImplementation((config) => {
      replaySignal = config.signal;
      return new Promise(() => {});
    });

    window.dispatchEvent(new Event('offline'));
    await expect(api.request({
      url: '/boards/2',
      method: 'post',
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

    window.dispatchEvent(new Event('online'));
    await vi.waitFor(() => expect(adapter).toHaveBeenCalledOnce());
    expect(replaySignal?.aborted).toBe(false);

    window.dispatchEvent(new Event('aac:auth-context-changed'));
    expect(replaySignal?.aborted).toBe(true);
    expect(useOfflineStore.getState().conflicts).toHaveLength(0);
  });
});
