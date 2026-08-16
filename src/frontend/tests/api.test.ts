import { afterEach, describe, expect, it, vi } from 'vitest';
import api, { apiOffline, extractError, isAuthFlowEndpoint } from '../src/lib/api';
import type { User } from '../src/types';
import { useAuthStore } from '../src/store/authStore';
import { useOfflineStore } from '../src/store/offlineStore';
import {
  readOfflineQueue,
  writeOfflineQueue,
} from '../src/lib/offlinePersistence';

const testUser = {
  id: 1,
  username: 'student1',
  user_type: 'student',
} as User;
const originalAdapter = api.defaults.adapter;

function authenticateOfflineTestUser() {
  useAuthStore.setState({ user: testUser, token: 'stale-token' });
}

describe('auth response handling', () => {
  afterEach(() => {
    // Restore globals before persistence cleanup; otherwise the non-auth 401
    // test leaves `window` undefined and marks storage unavailable for the
    // following replay tests.
    vi.unstubAllGlobals();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('aac:auth-logout'));
      window.dispatchEvent(new Event('online'));
    }
    useOfflineStore.getState().clearConflicts();
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
    });
    api.defaults.adapter = originalAdapter;
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('preserves supported backend error payload shapes', () => {
    expect(extractError({ response: { data: { detail: 'detail' } } }, 'fallback')).toBe('detail');
    expect(extractError({ response: { data: { error: 'error' } } }, 'fallback')).toBe('error');
    expect(extractError({ response: { data: { message: 'message' } } }, 'fallback')).toBe('message');
    expect(extractError({ message: 'client error' }, 'fallback')).toBe('client error');
  });

  it('recognizes auth endpoints whose 401 responses belong to the active flow', () => {
    expect(isAuthFlowEndpoint('/auth/token')).toBe(true);
    expect(isAuthFlowEndpoint('/auth/logout')).toBe(true);
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

  it('does not clear the session for an auth-flow 401', async () => {
    const clearSession = vi.fn();
    const state = useAuthStore.getState();
    vi.spyOn(useAuthStore, 'getState').mockReturnValue({ ...state, clearSession });

    await expect(api.request({
      url: '/auth/token',
      method: 'post',
      adapter: (config) => Promise.reject({
        config,
        response: { status: 401 },
      }),
    })).rejects.toMatchObject({ response: { status: 401 } });

    expect(clearSession).not.toHaveBeenCalled();
  });

  it('clears the session for a non-auth 401', async () => {
    const clearSession = vi.fn();
    const state = useAuthStore.getState();
    vi.spyOn(useAuthStore, 'getState').mockReturnValue({ ...state, clearSession });
    vi.stubGlobal('window', undefined);

    await expect(api.request({
      url: '/boards/1',
      method: 'get',
      adapter: (config) => Promise.reject({
        config,
        response: { status: 401 },
      }),
    })).rejects.toMatchObject({ response: { status: 401 } });

    expect(clearSession).toHaveBeenCalledOnce();
  });

  it('keeps an unauthorized replay as a visible conflict instead of clearing it on logout', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn().mockImplementation((config) => Promise.reject({
      config,
      response: { status: 401, data: { detail: 'access token expired' } },
    }));
    api.defaults.adapter = adapter;
    sessionStorage.setItem('aac-assistant-offline-queue-v1', JSON.stringify([{
      userId: testUser.id,
      config: { url: '/boards/replay-expired', method: 'post', data: { name: 'Keep me' } },
    }]));

    await apiOffline.resumeQueue();

    expect(adapter).toHaveBeenCalledOnce();
    expect(useAuthStore.getState().user).toEqual(testUser);
    expect(useOfflineStore.getState().conflicts).toEqual([
      expect.objectContaining({
        userId: testUser.id,
        error: 'access token expired',
      }),
    ]);
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
  });

  it('drops offline mutations when the session logs out before reconnecting', async () => {
    authenticateOfflineTestUser();
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

    vi.spyOn(api, 'post').mockResolvedValue({ data: { ok: true } } as never);
    await useAuthStore.getState().logout();
    expect(useOfflineStore.getState().conflicts).toHaveLength(0);

    window.dispatchEvent(new Event('online'));
    await Promise.resolve();
    expect(adapter).not.toHaveBeenCalled();
  });

  it('bounds queued offline mutations', async () => {
    authenticateOfflineTestUser();
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
    authenticateOfflineTestUser();
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
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).not.toBeNull();

    resolveFirst?.();
    await vi.waitFor(() => expect(secondAdapter).toHaveBeenCalledOnce());
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
  });

  it('does not queue unauthenticated offline mutations', async () => {
    const adapter = vi.fn();
    window.dispatchEvent(new Event('offline'));
    await expect(api.request({
      url: '/boards/anonymous',
      method: 'post',
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
    expect(adapter).not.toHaveBeenCalled();
  });

  it('does not persist non-JSON offline payloads', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn();
    window.dispatchEvent(new Event('offline'));
    const formData = new FormData();
    formData.append('file', new Blob(['audio']), 'audio.wav');

    await expect(api.request({
      url: '/learning/1/answer/voice',
      method: 'post',
      data: formData,
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
    expect(adapter).not.toHaveBeenCalled();
  });

  it('ignores malformed persisted queue data', async () => {
    authenticateOfflineTestUser();
    sessionStorage.setItem('aac-assistant-offline-queue-v1', '{not-json');

    await apiOffline.resumeQueue();

    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
  });

  it('replays a persisted mutation directly even when the browser is still offline', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn().mockResolvedValue({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    });
    api.defaults.adapter = adapter;
    sessionStorage.setItem('aac-assistant-offline-queue-v1', JSON.stringify([{
      userId: testUser.id,
      config: { url: '/boards/replay-while-offline', method: 'post', data: { name: 'Replay' } },
    }]));
    window.dispatchEvent(new Event('offline'));

    await apiOffline.resumeQueue();

    expect(adapter).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
  });

  it('discards a persisted request owned by another user without replaying it', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn();
    api.defaults.adapter = adapter;
    sessionStorage.setItem('aac-assistant-offline-queue-v1', JSON.stringify([{
      userId: 99,
      config: { url: '/boards/private', method: 'post', data: { name: 'Private' } },
    }]));

    await apiOffline.resumeQueue();

    expect(adapter).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
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

  it('restores a persisted mutation and applies the current token on replay', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn().mockResolvedValue({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    });
    api.defaults.adapter = adapter;
    sessionStorage.setItem('aac-assistant-offline-queue-v1', JSON.stringify([{
      userId: testUser.id,
      config: {
        url: '/boards/restored',
        method: 'post',
        data: { name: 'Restored' },
        headers: { Authorization: 'Bearer old-token' },
      },
    }]));

    await apiOffline.resumeQueue();

    expect(adapter).toHaveBeenCalledOnce();
    const replayConfig = adapter.mock.calls[0][0];
    expect(replayConfig.headers.Authorization).toBe('Bearer stale-token');
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
  });

  it('shares one in-flight replay when auth readiness and online events overlap', async () => {
    authenticateOfflineTestUser();
    let releaseReplay: (() => void) | undefined;
    const adapter = vi.fn().mockImplementation((config) => new Promise((resolve) => {
      releaseReplay = () => resolve({
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      });
    }));
    api.defaults.adapter = adapter;
    sessionStorage.setItem('aac-assistant-offline-queue-v1', JSON.stringify([{
      userId: testUser.id,
      config: { url: '/boards/once', method: 'post', data: { name: 'Once' } },
    }]));

    const firstReplay = apiOffline.resumeQueue();
    const secondReplay = apiOffline.resumeQueue();

    expect(secondReplay).toBe(firstReplay);
    await vi.waitFor(() => expect(adapter).toHaveBeenCalledOnce());
    releaseReplay?.();
    await firstReplay;
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
  });

  it('does not expose an unowned conflict to a later authenticated user', () => {
    useOfflineStore.getState().addConflict(
      { url: '/boards/anonymous', method: 'post' },
      'anonymous conflict',
    );
    expect(useOfflineStore.getState().conflicts).toHaveLength(1);

    useOfflineStore.getState().discardForeignConflicts(testUser.id);

    expect(useOfflineStore.getState().conflicts).toHaveLength(0);
  });

  it('preserves a valid FIFO prefix when persisted data exceeds the byte limit', () => {
    writeOfflineQueue([
      { userId: testUser.id, config: { url: '/boards/small', method: 'post', data: { ok: true } } },
      { userId: testUser.id, config: { url: '/boards/large', method: 'post', data: { value: 'x'.repeat(210_000) } } },
    ]);

    expect(readOfflineQueue()).toEqual([
      expect.objectContaining({ config: expect.objectContaining({ url: '/boards/small' }) }),
    ]);
  });

  it('does not replay a stale snapshot after a storage write failure', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn();
    window.dispatchEvent(new Event('offline'));

    await expect(api.request({
      url: '/boards/first-before-storage-failure',
      method: 'post',
      data: { name: 'First' },
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

    const setItemFailure = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });

    try {
      await expect(api.request({
        url: '/boards/second-storage-failure',
        method: 'post',
        data: { name: 'Second' },
        adapter,
      })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

      expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
      expect(useOfflineStore.getState().conflicts).toHaveLength(2);

      window.dispatchEvent(new Event('online'));
      await Promise.resolve();
      expect(adapter).not.toHaveBeenCalled();
    } finally {
      setItemFailure.mockRestore();
    }
  });

  it('surfaces a mutation that cannot fit storage as a visible conflict', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn();
    window.dispatchEvent(new Event('offline'));

    await expect(api.request({
      url: '/boards/large-offline',
      method: 'post',
      data: { value: 'x'.repeat(210_000) },
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

    expect(useOfflineStore.getState().conflicts).toEqual([
      expect.objectContaining({
        error: 'Offline mutation could not be persisted; storage limit reached',
        userId: testUser.id,
      }),
    ]);
    expect(sessionStorage.getItem('aac-assistant-offline-queue-v1')).toBeNull();
    expect(adapter).not.toHaveBeenCalled();
  });

  it('does not restore another user’s persisted conflict', async () => {
    authenticateOfflineTestUser();
    useOfflineStore.getState().addConflict(
      { url: '/boards/private', method: 'post', data: { name: 'Private' } },
      'conflict',
      testUser.id,
    );
    expect(useOfflineStore.getState().conflicts).toHaveLength(1);

    useAuthStore.setState({
      user: { ...testUser, id: 2, username: 'other-user' },
      token: 'other-token',
    });
    window.dispatchEvent(new Event('aac:auth-ready'));

    expect(useOfflineStore.getState().conflicts).toHaveLength(0);
    expect(sessionStorage.getItem('aac-assistant-offline-conflicts-v1')).toBeNull();
  });

  it('aborts a replay already started when the session logs out', async () => {
    authenticateOfflineTestUser();
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

  it('does not resume a stale snapshot when storage cleanup also fails', async () => {
    authenticateOfflineTestUser();
    const adapter = vi.fn();
    window.dispatchEvent(new Event('offline'));

    await expect(api.request({
      url: '/boards/stale-snapshot',
      method: 'post',
      data: { name: 'Stale' },
      adapter,
    })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

    const setItemFailure = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    const removeItemFailure = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('storage locked');
    });

    try {
      await expect(api.request({
        url: '/boards/cleanup-failure',
        method: 'post',
        data: { name: 'Cleanup failure' },
        adapter,
      })).rejects.toMatchObject({ code: 'ERR_OFFLINE' });

      await apiOffline.resumeQueue();
      expect(adapter).not.toHaveBeenCalled();
      expect(useOfflineStore.getState().conflicts).toHaveLength(2);
    } finally {
      setItemFailure.mockRestore();
      removeItemFailure.mockRestore();
    }
  });
});
