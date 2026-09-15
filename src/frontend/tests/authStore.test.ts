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

    expect(post).toHaveBeenCalledWith('/auth/refresh', { refresh_token: 'valid-refresh-token' });
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

  it('sends the refresh token in the request body, not the URL', async () => {
    seedSession('not-a-jwt');
    const refreshedToken = makeJwt(Math.floor(Date.now() / 1000) + 7200);
    const post = vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: refreshedToken },
    } as never);

    await useAuthStore.getState().checkAuth();

    expect(post).toHaveBeenCalledTimes(1);
    const [url, body, config] = post.mock.calls[0];
    expect(url).toBe('/auth/refresh');
    expect(body).toEqual({ refresh_token: 'valid-refresh-token' });
    // No query-string credential channel may be used.
    expect(config?.params).toBeUndefined();
  });

  it('persists the rotated refresh token from the refresh response (H3)', async () => {
    seedSession('not-a-jwt');
    const post = vi.spyOn(api, 'post').mockResolvedValue({
      data: {
        access_token: makeJwt(Math.floor(Date.now() / 1000) + 7200),
        refresh_token: 'rotated-refresh-token',
      },
    } as never);

    expect(await useAuthStore.getState().refreshAccessToken()).toBe(true);

    expect(post).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().refreshToken).toBe('rotated-refresh-token');
  });

  it('keeps the current refresh token when the server does not rotate it', async () => {
    seedSession('not-a-jwt');
    vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: makeJwt(Math.floor(Date.now() / 1000) + 7200) },
    } as never);

    expect(await useAuthStore.getState().refreshAccessToken()).toBe(true);

    expect(useAuthStore.getState().refreshToken).toBe('valid-refresh-token');
  });

  it('discards a deferred refresh success published after logout', async () => {
    seedSession('not-a-jwt');
    let resolveRefresh: ((value: { data: { access_token: string } }) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation(
      () => new Promise((resolve) => {
        resolveRefresh = resolve;
      }) as never,
    );

    const refreshPromise = useAuthStore.getState().refreshAccessToken();
    expect(resolveRefresh).toBeDefined();

    // Logout ends the session while the refresh request is in flight.
    vi.spyOn(api, 'post').mockResolvedValue({ data: { ok: true } } as never);
    await useAuthStore.getState().logout();

    resolveRefresh!({ data: { access_token: makeJwt(Math.floor(Date.now() / 1000) + 7200) } });
    expect(await refreshPromise).toBe(false);

    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('discards a deferred refresh success after a newer login wins', async () => {
    const userA = { ...user, id: 7, username: 'user-a' };
    const userB = { ...user, id: 8, username: 'user-b' };
    seedSession('not-a-jwt');

    let resolveStaleRefresh: ((value: { data: { access_token: string } }) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation(
      () => new Promise((resolve) => {
        if (!resolveStaleRefresh) {
          resolveStaleRefresh = resolve;
        }
        return new Promise<void>(() => {});
      }) as never,
    );

    const staleRefresh = useAuthStore.getState().refreshAccessToken();
    expect(resolveStaleRefresh).toBeDefined();

    // User B logs in while A's refresh is still pending.
    const tokenB = makeJwt(Math.floor(Date.now() / 1000) + 3600, userB.id);
    vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: tokenB, refresh_token: 'refresh-b' },
    } as never);
    vi.spyOn(api, 'get').mockResolvedValue({ data: userB } as never);
    await useAuthStore.getState().login(userB.username, 'password');

    resolveStaleRefresh!({
      data: { access_token: makeJwt(Math.floor(Date.now() / 1000) + 7200, userA.id) },
    });
    expect(await staleRefresh).toBe(false);

    expect(useAuthStore.getState().user).toEqual(userB);
    expect(useAuthStore.getState().token).toBe(tokenB);
    expect(useAuthStore.getState().refreshToken).toBe('refresh-b');
  });

  it('does not clear a newer session when a stale refresh fails', async () => {
    seedSession('not-a-jwt');
    let rejectStaleRefresh: ((error: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation(
      () => new Promise((_resolve, reject) => {
        if (!rejectStaleRefresh) {
          rejectStaleRefresh = reject;
        }
        return new Promise<void>(() => {});
      }) as never,
    );

    const staleRefresh = useAuthStore.getState().refreshAccessToken();
    expect(rejectStaleRefresh).toBeDefined();

    // A new login takes over before the stale refresh fails.
    const userB = { ...user, id: 8, username: 'user-b' };
    const tokenB = makeJwt(Math.floor(Date.now() / 1000) + 3600, userB.id);
    vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: tokenB, refresh_token: 'refresh-b' },
    } as never);
    vi.spyOn(api, 'get').mockResolvedValue({ data: userB } as never);
    await useAuthStore.getState().login(userB.username, 'password');

    rejectStaleRefresh!({ response: { status: 401 } });
    expect(await staleRefresh).toBe(false);

    // The newer session must remain fully intact.
    expect(useAuthStore.getState().user).toEqual(userB);
    expect(useAuthStore.getState().token).toBe(tokenB);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it('coalesces simultaneous expired-token refreshes for the same session', async () => {
    seedSession('not-a-jwt');
    let refreshCalls = 0;
    let releaseRefresh: (() => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation(
      () => {
        refreshCalls += 1;
        return new Promise((resolve) => {
          releaseRefresh = () => resolve({
            data: { access_token: makeJwt(Math.floor(Date.now() / 1000) + 7200) },
          });
        }) as never;
      },
    );

    const first = useAuthStore.getState().refreshAccessToken();
    const second = useAuthStore.getState().refreshAccessToken();
    const third = useAuthStore.getState().refreshAccessToken();

    releaseRefresh?.();
    // All callers share one in-flight HTTP request and resolve to the same
    // (truthy) result. refreshAccessToken is an async function, so callers
    // receive distinct wrapper promises even when the request is coalesced.
    expect(refreshCalls).toBe(1);
    expect(await Promise.all([first, second, third])).toEqual([true, true, true]);
    expect(refreshCalls).toBe(1);
  });

  it('does not coalesce a refresh request from a different session token', async () => {
    seedSession('not-a-jwt');
    let refreshCalls = 0;
    vi.spyOn(api, 'post').mockImplementation(
      () => {
        refreshCalls += 1;
        return new Promise(() => {});
      },
    ) as never;

    const first = useAuthStore.getState().refreshAccessToken();

    // Another identity takes over with its own refresh token while the first
    // request is still pending: the second caller must issue its own request
    // instead of awaiting a result that will be discarded.
    useAuthStore.setState({ refreshToken: 'other-session-token' });
    const second = useAuthStore.getState().refreshAccessToken();
    expect(second).not.toBe(first);
    expect(refreshCalls).toBe(2);
  });

  it('does not stamp a stale login failure onto a newer session (N5/D12)', async () => {
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600));
    const userB = { ...user, id: 8, username: 'user-b' };
    let rejectStaleLogin: ((error: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/auth/token' && !rejectStaleLogin) {
        return new Promise((_resolve, reject) => {
          rejectStaleLogin = reject;
        }) as never;
      }
      const tokenB = makeJwt(Math.floor(Date.now() / 1000) + 3600, userB.id);
      return Promise.resolve({
        data: { access_token: tokenB, refresh_token: 'refresh-b' },
      }) as never;
    });
    vi.spyOn(api, 'get').mockResolvedValue({ data: userB } as never);

    const staleLogin = useAuthStore.getState().login('user-a', 'wrong');
    expect(useAuthStore.getState().isLoading).toBe(true);

    // A newer login wins while the stale attempt is still in flight.
    await useAuthStore.getState().login(userB.username, 'password');
    rejectStaleLogin!({ response: { status: 401 } });
    await expect(staleLogin).rejects.toBeDefined();

    // The newer session must keep its clean error state and spinner state.
    expect(useAuthStore.getState().user).toEqual(userB);
    expect(useAuthStore.getState().error).toBeNull();
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('does not stamp a stale setup failure onto a newer session (N5/D12)', async () => {
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600));
    const admin = { ...user, id: 8, username: 'admin-b' };
    let rejectStaleSetup: ((error: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/auth/setup' && !rejectStaleSetup) {
        return new Promise((_resolve, reject) => {
          rejectStaleSetup = reject;
        }) as never;
      }
      const token = makeJwt(Math.floor(Date.now() / 1000) + 3600, admin.id);
      return Promise.resolve({
        data: { access_token: token, refresh_token: 'refresh-b', user: admin },
      }) as never;
    });

    vi.spyOn(api, 'get').mockResolvedValue({ data: admin } as never);
    const staleSetup = useAuthStore.getState().setupAdmin({
      username: admin.username,
      password: 'StrongPass123',
      display_name: admin.display_name,
    } as never);
    expect(useAuthStore.getState().isLoading).toBe(true);

    await useAuthStore.getState().login(admin.username, 'password');
    rejectStaleSetup!({ response: { status: 400 } });
    await expect(staleSetup).rejects.toBeDefined();

    expect(useAuthStore.getState().user).toEqual(admin);
    expect(useAuthStore.getState().error).toBeNull();
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('does not cancel an in-flight login when a registration starts (Q2)', async () => {
    // register publishes no session state, so it must not bump the session
    // epoch — incrementing it discarded the in-flight login's success publish.
    const freshUser = { ...user, id: 9, username: 'fresh' };
    const freshToken = makeJwt(Math.floor(Date.now() / 1000) + 3600, freshUser.id);
    let resolveLogin: ((value: unknown) => void) | undefined;
    let resolveRegister: ((value: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/auth/token') {
        return new Promise((resolve) => {
          resolveLogin = resolve;
        }) as never;
      }
      if (url === '/auth/register') {
        return new Promise((resolve) => {
          resolveRegister = resolve;
        }) as never;
      }
      return Promise.resolve({ data: {} }) as never;
    });
    vi.spyOn(api, 'get').mockResolvedValue({ data: freshUser } as never);

    const loginPromise = useAuthStore.getState().login('fresh', 'password');
    const registerPromise = useAuthStore.getState().register({
      username: 'fresh',
      password: 'StrongPass123',
      display_name: 'Fresh',
    } as never);

    resolveLogin!({ data: { access_token: freshToken, refresh_token: 'refresh-fresh' } });
    await loginPromise;

    // The login's success must survive the concurrent registration.
    expect(useAuthStore.getState().token).toBe(freshToken);
    expect(useAuthStore.getState().user).toEqual(freshUser);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);

    // The registration settling later must not disturb the new session.
    resolveRegister!({ data: { ok: true } });
    await registerPromise;
    expect(useAuthStore.getState().token).toBe(freshToken);
    expect(useAuthStore.getState().error).toBeNull();
  });

  it('keeps the login spinner while a concurrent registration settles (Q2)', async () => {
    // A registration shares the login's session epoch, so the spinner must be
    // tracked by its own token: settling the registration may not clear a
    // spinner an in-flight login still owns.
    const freshUser = { ...user, id: 11, username: 'spinner' };
    const freshToken = makeJwt(Math.floor(Date.now() / 1000) + 3600, freshUser.id);
    let resolveLogin: ((value: unknown) => void) | undefined;
    let resolveRegister: ((value: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/auth/token') {
        return new Promise((resolve) => {
          resolveLogin = resolve;
        }) as never;
      }
      if (url === '/auth/register') {
        return new Promise((resolve) => {
          resolveRegister = resolve;
        }) as never;
      }
      return Promise.resolve({ data: {} }) as never;
    });
    vi.spyOn(api, 'get').mockResolvedValue({ data: freshUser } as never);

    const loginPromise = useAuthStore.getState().login('spinner', 'password');
    const registerPromise = useAuthStore.getState().register({
      username: 'spinner',
      password: 'StrongPass123',
      display_name: 'Spinner',
    } as never);

    // The registration resolves first; the login is still pending.
    resolveRegister!({ data: { ok: true } });
    await registerPromise;
    expect(useAuthStore.getState().isLoading).toBe(true);

    resolveLogin!({ data: { access_token: freshToken, refresh_token: 'refresh-spinner' } });
    await loginPromise;
    expect(useAuthStore.getState().isLoading).toBe(false);
    expect(useAuthStore.getState().token).toBe(freshToken);
  });

  it('does not stamp a stale registration failure onto a newer session (Q2)', async () => {
    let rejectRegister: ((error: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/auth/register') {
        return new Promise((_resolve, reject) => {
          rejectRegister = reject;
        }) as never;
      }
      return Promise.resolve({
        data: {
          access_token: makeJwt(Math.floor(Date.now() / 1000) + 3600),
          refresh_token: 'refresh-a',
        },
      }) as never;
    });
    vi.spyOn(api, 'get').mockResolvedValue({ data: user } as never);

    const registerPromise = useAuthStore.getState().register({
      username: 'new-user',
      password: 'StrongPass123',
      display_name: 'New User',
    } as never);
    expect(useAuthStore.getState().isLoading).toBe(true);

    // A newer session wins while the registration is still in flight.
    await useAuthStore.getState().login('tester', 'password');

    rejectRegister!({ response: { status: 400 } });
    await expect(registerPromise).rejects.toBeDefined();

    expect(useAuthStore.getState().user).toEqual(user);
    expect(useAuthStore.getState().error).toBeNull();
    expect(useAuthStore.getState().isLoading).toBe(false);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it('does not leave the spinner stuck when logout interrupts a login (N5)', async () => {
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600));
    let rejectLogin: ((error: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/auth/token') {
        return new Promise((_resolve, reject) => {
          rejectLogin = reject;
        }) as never;
      }
      return Promise.resolve({ data: { ok: true } }) as never;
    });

    const loginPromise = useAuthStore.getState().login('tester', 'password');
    expect(useAuthStore.getState().isLoading).toBe(true);

    // Logout clears the session (and the spinner) while the login is pending.
    await useAuthStore.getState().logout();
    expect(useAuthStore.getState().isLoading).toBe(false);

    rejectLogin!({ response: { status: 401 } });
    await expect(loginPromise).rejects.toBeDefined();

    expect(useAuthStore.getState().isLoading).toBe(false);
    expect(useAuthStore.getState().error).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('clears the spinner when a non-loading checkAuth invalidates a failed login (N5)', async () => {
    // checkAuth bumps the session epoch without owning the spinner; a stale
    // login failure must still clear the spinner it started instead of
    // leaving the UI loading forever.
    seedSession(makeJwt(Math.floor(Date.now() / 1000) + 3600));
    let rejectLogin: ((error: unknown) => void) | undefined;
    vi.spyOn(api, 'post').mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectLogin = reject;
        }) as never,
    );

    const loginPromise = useAuthStore.getState().login('tester', 'wrong');
    expect(useAuthStore.getState().isLoading).toBe(true);

    await useAuthStore.getState().checkAuth();
    rejectLogin!({ response: { status: 401 } });
    await expect(loginPromise).rejects.toBeDefined();

    expect(useAuthStore.getState().isLoading).toBe(false);
    expect(useAuthStore.getState().error).toBeNull();
  });

  it('clears the persisted session before awaiting server revocation (A16)', async () => {
    let releaseRevocation: () => void = () => {};
    vi.spyOn(api, 'post').mockImplementation(
      () =>
        new Promise((resolve) => {
          releaseRevocation = () => resolve({ data: { ok: true } } as never);
        }) as never,
    );

    const logoutPromise = useAuthStore.getState().logout();

    // Revocation is still in flight, yet the persisted auth-storage is already
    // cleared: a /login navigation that does not await logout cannot rehydrate
    // the stale session.
    expect(persistedState()).toMatchObject({ token: null, isAuthenticated: false });

    releaseRevocation();
    await logoutPromise;
    expect(persistedState()).toMatchObject({ token: null, isAuthenticated: false });
  });

});
