/**
 * A15 — the persisted session must be validated/refreshed before the store
 * signals `aac:auth-ready`, because that event is what releases the offline
 * replay queue. Reloading with an expired access token would otherwise replay
 * every queued mutation with the dead token, turning each into a manual
 * conflict instead of a silent refresh-and-retry.
 *
 * Lives in its own file: it asserts the persist middleware's own
 * onRehydrateStorage hook, so it needs a module registry that no other spec has
 * already hydrated and mutated.
 */
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

function makeJwt(exp: number) {
  const encode = (value: object) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({
    sub: String(user.id),
    exp,
    user_id: user.id,
  })}.signature`;
}

describe('auth rehydration gating (A15)', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      error: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('refreshes the persisted session before signalling auth-ready', async () => {
    const expired = makeJwt(Math.floor(Date.now() / 1000) - 60);
    // Written through the real persist writer (setState), so the persisted
    // shape and version match what the middleware reads back.
    useAuthStore.setState({
      user,
      token: expired,
      refreshToken: 'valid-refresh-token',
      isAuthenticated: true,
      sessionExpiresAt: 0,
      error: null,
    });

    const order: string[] = [];
    vi.spyOn(api, 'post').mockImplementation(async (url: string) => {
      order.push(`post:${url}`);
      return {
        data: { access_token: makeJwt(Math.floor(Date.now() / 1000) + 3600) },
      } as never;
    });
    // Capture the event without running other listeners: the assertion is about
    // when the store signals readiness, not who else reacts to it.
    const dispatched: string[] = [];
    vi.spyOn(window, 'dispatchEvent').mockImplementation((event: Event) => {
      dispatched.push(event.type);
      return true;
    });

    useAuthStore.persist.rehydrate();
    await vi.waitFor(() => expect(dispatched).toContain('aac:auth-ready'));

    // The refresh completes before the queue is told it may flush; the ready
    // event is dispatched in that promise's finally block, so a recorded
    // refresh request proves the ordering.
    expect(order).toEqual(['post:/auth/refresh']);
    expect(useAuthStore.getState().token).not.toBe(expired);
  });
});
