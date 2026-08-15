import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../src/lib/api';
import { useAuthStore } from '../src/store/authStore';

const user = {
  id: 7,
  username: 'tester',
  display_name: 'Test User',
  user_type: 'student' as const,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

function makeJwt(exp: number, userId = user.id) {
  const encode = (value: object) => btoa(JSON.stringify(value))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({
    sub: String(userId),
    exp,
    user_id: userId,
  })}.signature`;
}

function seedSession(token: string) {
  useAuthStore.setState({
    user,
    token,
    refreshToken: 'valid-refresh-token',
    isAuthenticated: true,
    sessionExpiresAt: Date.now() + 60_000,
    error: null,
  });
}

function persistedState() {
  const stored = localStorage.getItem('auth-storage');
  expect(stored).not.toBeNull();
  return JSON.parse(stored as string).state;
}

describe('auth session refresh robustness', () => {
  beforeEach(() => {
    localStorage.clear();
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('dispatches an auth-context event before switching users on login', async () => {
    const nextUser = {
      ...user,
      id: 8,
      username: 'next-user',
    };
    const token = makeJwt(Math.floor(Date.now() / 1000) + 3600, nextUser.id);
    const post = vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: token, refresh_token: 'next-refresh-token' },
    } as never);
    vi.spyOn(api, 'get').mockResolvedValue({ data: nextUser } as never);
    const dispatch = vi.spyOn(window, 'dispatchEvent');

    await useAuthStore.getState().login(nextUser.username, 'password');

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'aac:auth-context-changed' }));
    expect(useAuthStore.getState().user).toEqual(nextUser);
    expect(post).toHaveBeenCalledWith('/auth/token', expect.any(URLSearchParams), expect.anything());
  });

  it('refreshes an undecodable access token and keeps the session', async () => {
    seedSession('not-a-jwt');
    const refreshedToken = makeJwt(Math.floor(Date.now() / 1000) + 7200);
    const post = vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: refreshedToken },
    } as never);

    await useAuthStore.getState().checkAuth();

    expect(post).toHaveBeenCalledWith('/auth/refresh', null, {
      params: { refresh_token: 'valid-refresh-token' },
    });
    expect(useAuthStore.getState()).toMatchObject({
      user,
      token: refreshedToken,
      refreshToken: 'valid-refresh-token',
      isAuthenticated: true,
    });
    expect(persistedState()).toMatchObject({
      user,
      token: refreshedToken,
      refreshToken: 'valid-refresh-token',
      isAuthenticated: true,
    });
  });

  it('refreshes an expired decodable access token and keeps the session', async () => {
    seedSession(makeJwt(Math.floor(Date.now() / 1000) - 60));
    const refreshedToken = makeJwt(Math.floor(Date.now() / 1000) + 7200);
    const post = vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: refreshedToken },
    } as never);

    await useAuthStore.getState().checkAuth();

    expect(post).toHaveBeenCalledOnce();
    expect(useAuthStore.getState()).toMatchObject({
      token: refreshedToken,
      refreshToken: 'valid-refresh-token',
      isAuthenticated: true,
    });
  });

  it('fully clears an undecodable session after an online refresh failure', async () => {
    seedSession('not-a-jwt');
    vi.spyOn(api, 'post').mockRejectedValue({
      response: { status: 401 },
    });

    await useAuthStore.getState().checkAuth();

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      error: null,
    });
    expect(persistedState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
    });
  });

  it('fully clears an expired session after an online refresh failure', async () => {
    seedSession(makeJwt(Math.floor(Date.now() / 1000) - 60));
    vi.spyOn(api, 'post').mockRejectedValue({
      response: { status: 401 },
    });

    await useAuthStore.getState().checkAuth();

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      error: null,
    });
    expect(persistedState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
    });
  });

  it('fully clears the session when fetching the current user fails online', async () => {
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600));
    useAuthStore.setState({ user: null });
    vi.spyOn(api, 'get').mockRejectedValue({
      response: { status: 401 },
    });

    await useAuthStore.getState().checkAuth();

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      error: null,
    });
    expect(persistedState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
    });
  });

  it('fully clears stale session fields when no access token remains', async () => {
    useAuthStore.setState({ token: null });

    await useAuthStore.getState().checkAuth();

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      error: null,
    });
    expect(persistedState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
    });
  });

  it('revokes the server session and clears every persisted session field on logout', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { ok: true } } as never);

    await useAuthStore.getState().logout();

    expect(post).toHaveBeenCalledWith('/auth/logout', null, {
      headers: { Authorization: expect.stringContaining('Bearer ') },
    });
    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      error: null,
    });
    expect(persistedState()).toMatchObject({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
    });
  });

  it('preserves the session when refresh fails offline', async () => {
    seedSession('not-a-jwt');
    vi.spyOn(api, 'post').mockRejectedValue({
      code: 'ERR_OFFLINE',
      message: 'offline',
    });
    vi.stubGlobal('navigator', { onLine: false });

    await useAuthStore.getState().checkAuth();

    expect(useAuthStore.getState()).toMatchObject({
      user,
      token: 'not-a-jwt',
      refreshToken: 'valid-refresh-token',
      isAuthenticated: true,
      sessionExpiresAt: expect.any(Number),
    });
    expect(persistedState()).toMatchObject({
      user,
      token: 'not-a-jwt',
      refreshToken: 'valid-refresh-token',
      isAuthenticated: true,
    });
  });
});
