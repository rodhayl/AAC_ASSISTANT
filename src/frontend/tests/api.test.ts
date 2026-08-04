import { afterEach, describe, expect, it, vi } from 'vitest';
import api, { isAuthFlowEndpoint } from '../src/lib/api';
import { useAuthStore } from '../src/store/authStore';

describe('auth response handling', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('recognizes auth endpoints whose 401 responses belong to the active flow', () => {
    expect(isAuthFlowEndpoint('/auth/token')).toBe(true);
    expect(isAuthFlowEndpoint('/api/auth/refresh?refresh_token=token')).toBe(true);
    expect(isAuthFlowEndpoint('https://localhost/api/auth/change-password')).toBe(true);
    expect(isAuthFlowEndpoint('/auth/tokenize')).toBe(false);
    expect(isAuthFlowEndpoint('/boards/1')).toBe(false);
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
});
