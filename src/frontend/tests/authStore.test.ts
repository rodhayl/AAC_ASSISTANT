import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../src/lib/api';
import { useAuthStore } from '../src/store/authStore';
import { useThemeStore } from '../src/store/themeStore';

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

  it('syncs the persisted dark mode and high contrast flags into the theme store on login', async () => {
    const nextUser = {
      ...user,
      settings: { dark_mode: true, high_contrast: true },
    };
    const token = makeJwt(Math.floor(Date.now() / 1000) + 3600);
    vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: token, refresh_token: 'next-refresh-token' },
    } as never);
    vi.spyOn(api, 'get').mockResolvedValue({ data: nextUser } as never);

    useThemeStore.getState().setDarkMode(false);
    useThemeStore.getState().setHighContrast(false);

    await useAuthStore.getState().login(nextUser.username, 'password');

    expect(useThemeStore.getState().darkMode).toBe(true);
    expect(useThemeStore.getState().highContrast).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(true);
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

  it('does not publish a stale user-details response after the session changes', async () => {
    // checkAuth starts with a persisted token but no user object, so it must
    // fetch user details; the fetch is held in flight while a logout (new
    // epoch) happens, so the late response must not resurrect a session.
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600));
    useAuthStore.setState({ user: null });

    let resolveFetch: ((value: { data: typeof user }) => void) | undefined;
    const getSpy = vi.spyOn(api, 'get').mockImplementation(
      () => new Promise((resolve) => {
        resolveFetch = resolve;
      }) as never,
    );

    const checkAuthPromise = useAuthStore.getState().checkAuth();
    expect(getSpy).toHaveBeenCalledTimes(1);
    expect(resolveFetch).toBeDefined();

    // Session ends while the fetch is in flight.
    vi.spyOn(api, 'post').mockResolvedValue({ data: { ok: true } } as never);
    await useAuthStore.getState().logout();

    resolveFetch!({ data: user });
    await checkAuthPromise;

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      token: null,
      isAuthenticated: false,
    });
    expect(persistedState()).toMatchObject({ user: null, token: null, isAuthenticated: false });
  });

  it('does not publish a stale user-details response after a newer login wins', async () => {
    // Same race on the login path: user A's checkAuth must not overwrite
    // user B's session when it finally resolves.
    const userA = { ...user, id: 7, username: 'user-a' };
    const userB = { ...user, id: 8, username: 'user-b' };
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600, userA.id));
    useAuthStore.setState({ user: null });

    let resolveStaleFetch: ((value: { data: typeof userA }) => void) | undefined;
    vi.spyOn(api, 'get').mockImplementation(
      () => new Promise((resolve) => {
        resolveStaleFetch = resolve;
      }) as never,
    );

    const staleCheck = useAuthStore.getState().checkAuth();
    expect(resolveStaleFetch).toBeDefined();

    // User B logs in while user A's details fetch is still pending.
    const tokenB = makeJwt(Math.floor(Date.now() / 1000) + 3600, userB.id);
    vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: tokenB, refresh_token: 'refresh-b' },
    } as never);
    // After login's own fetch resolves with B, the mock is exhausted.
    vi.spyOn(api, 'get').mockResolvedValue({ data: userB } as never);

    await useAuthStore.getState().login(userB.username, 'password');

    resolveStaleFetch!({ data: userA });
    await staleCheck;

    expect(useAuthStore.getState().user).toEqual(userB);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });
});
