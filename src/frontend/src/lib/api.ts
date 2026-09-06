import axios, { AxiosHeaders } from 'axios';
import type { AxiosRequestConfig } from 'axios';
import { getAuthState } from './authState';
import {
  errorMessageOf,
  errorPayloadOf,
  isCancelledError,
} from './httpErrors';
import { config } from '../config';
import {
  clearOfflinePersistence,
  readOfflineQueue,
  removeAuthorizationHeader,
  sanitizeOfflineConfig,
  writeOfflineQueue,
  type PersistedOfflineQueueItem,
} from './offlinePersistence';
import { useOfflineStore } from '../store/offlineStore';

export function extractError(error: unknown, fallback: string): string {
  const payload = errorPayloadOf(error);
  const detail = payload?.data?.detail;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((entry: unknown) => {
        if (
          entry &&
          typeof entry === 'object' &&
          'msg' in entry &&
          typeof entry.msg === 'string'
        ) {
          return entry.msg;
        }
        return String(entry);
      })
      .join(', ');
  }

  if (typeof detail === 'object' && detail !== null) {
    return JSON.stringify(detail);
  }

  const responseError = payload?.data?.error;
  if (typeof responseError === 'string' && responseError) return responseError;

  const responseMessage = payload?.data?.message;
  if (typeof responseMessage === 'string' && responseMessage) return responseMessage;

  return errorMessageOf(error) ?? fallback;
}

const api = axios.create({
  baseURL: config.API_BASE_URL,
  timeout: 30000, // 30 seconds timeout
});

// Per-endpoint timeout overrides for operations that legitimately run longer
// than the 30s default. Local Whisper transcription and LLM board-suggestion
// generation can take minutes on modest hardware; without an override the
// client aborts at 30s and shows an error while the server keeps working.
// Values are ceilings, not expectations: a stalled request still fails.
const LONG_REQUEST_TIMEOUT_MS: Readonly<Record<string, number>> = {
  // POST /boards/{id}/ai/suggestions — LLM suggestion generation.
  '/ai/suggestions': 120_000,
  // POST /learning/{id}/answer/voice — local Whisper transcription upload.
  '/answer/voice': 300_000,
};

function resolveRequestTimeout(url: string | undefined): number | undefined {
  if (!url) return undefined;
  const pathname = pathnameOf(url);
  if (!pathname) return undefined;
  for (const [suffix, timeout] of Object.entries(LONG_REQUEST_TIMEOUT_MS)) {
    if (pathname.endsWith(suffix)) return timeout;
  }
  return undefined;
}

const AUTH_FLOW_ENDPOINTS = new Set([
  '/auth/token',
  '/auth/refresh',
  '/auth/change-password',
  '/auth/logout',
]);

const OFFLINE_EXCLUDED_ENDPOINTS = new Set([
  ...AUTH_FLOW_ENDPOINTS,
  '/auth/register',
  '/auth/logout',
]);

function pathnameOf(url: string): string | null {
  try {
    return new URL(url, 'http://localhost').pathname.replace(/^\/api(?=\/)/, '');
  } catch {
    return null;
  }
}

export function isAuthFlowEndpoint(url?: string): boolean {
  if (!url) return false;
  const pathname = pathnameOf(url);
  return pathname !== null && AUTH_FLOW_ENDPOINTS.has(pathname);
}

function isOfflineExcludedEndpoint(url?: string): boolean {
  if (!url) return false;
  const pathname = pathnameOf(url);
  return pathname !== null && OFFLINE_EXCLUDED_ENDPOINTS.has(pathname);
}

let offline = typeof navigator !== 'undefined' ? !navigator.onLine : false;
const MAX_OFFLINE_QUEUE_SIZE = 100;
const OFFLINE_REPLAY: unique symbol = Symbol('offline-replay');
type OfflineReplayConfig = AxiosRequestConfig & { [OFFLINE_REPLAY]?: true };
// Marks a request retried after a silent token refresh so a second 401 cannot
// loop: one refresh-and-retry per request, then fall back to logout.
const RETRIED_AFTER_REFRESH: unique symbol = Symbol('retried-after-refresh');
type RefreshRetryConfig = AxiosRequestConfig & { [RETRIED_AFTER_REFRESH]?: true };
type QueuedRequest = { config: AxiosRequestConfig; userId: number };
function readQueuedRequests(): QueuedRequest[] {
  return readOfflineQueue().map((item) => ({
    config: item.config,
    userId: item.userId,
  }));
}

const queue: QueuedRequest[] = readQueuedRequests();
const replayControllers = new Set<AbortController>();
let replayGeneration = 0;
let activeFlush: Promise<void> | null = null;

function accessTokenIsExpired(token: string | null): boolean {
  // The server remains the authority for signature validation. This local
  // check only decides whether a 401 may use the refresh-token flow; an
  // unexpired token that the server rejected (for example, a forged token)
  // must log out instead of being silently replaced.
  if (!token) return true;
  try {
    const payload = token.split('.')[1];
    if (!payload) return false;
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const decoded = JSON.parse(atob(padded));
    return typeof decoded.exp === 'number' && decoded.exp * 1000 <= Date.now();
  } catch {
    return false;
  }
}

function persistQueue(): void {
  const durableEntries: Array<{
    item: QueuedRequest;
    persisted: PersistedOfflineQueueItem;
  }> = [];
  const nonDurableItems: QueuedRequest[] = [];

  queue.forEach((item) => {
    const safeConfig = sanitizeOfflineConfig(item.config);
    if (!safeConfig) {
      nonDurableItems.push(item);
      return;
    }
    durableEntries.push({
      item,
      persisted: { config: safeConfig, userId: item.userId },
    });
  });

  const persistedCount = writeOfflineQueue(durableEntries.map(({ persisted }) => persisted));
  if (persistedCount < 0) {
    const discardedItems = queue.splice(0).map((item) => ({
      item,
      error: 'Offline mutation could not be persisted; browser storage is unavailable',
    }));
    discardedItems.forEach(({ item, error }) => {
      useOfflineStore.getState().addConflict(item.config, error, item.userId);
    });
    return;
  }

  const droppedItems = durableEntries.slice(persistedCount).map(({ item }) => ({
    item,
    error: 'Offline mutation could not be persisted; storage limit reached',
  }));
  const discardedItems = [
    ...nonDurableItems.map((item) => ({
      item,
      error: 'Offline mutation contains data that cannot be safely persisted',
    })),
    ...droppedItems,
  ];
  if (discardedItems.length === 0) return;

  // A storage byte/quota limit or unsupported payload must never turn a
  // communication mutation into silent data loss. Remove entries that are not
  // durable and surface them in the existing conflict UI so the user can
  // retry them intentionally.
  discardedItems.forEach(({ item, error }) => {
    const index = queue.indexOf(item);
    if (index >= 0) queue.splice(index, 1);
    useOfflineStore.getState().addConflict(item.config, error, item.userId);
  });
}

function hasAuthenticatedOwner(item: QueuedRequest): boolean {
  const activeUserId = getAuthState().user?.id;
  return activeUserId === item.userId;
}

async function flushQueue() {
  if (queue.length === 0 || !getAuthState().user?.id) return;

  // Keep the current request in storage until it succeeds. A browser or
  // process crash during an in-flight replay must not silently lose a user's
  // mutation.
  const generation = replayGeneration;
  while (queue.length > 0) {
    if (generation !== replayGeneration) return;

    const item = queue[0];
    if (!hasAuthenticatedOwner(item)) {
      // A stale persisted request must never be replayed by another user.
      queue.shift();
      persistQueue();
      continue;
    }

    const controller = new AbortController();
    replayControllers.add(controller);
    try {
      await api.request({
        ...item.config,
        signal: controller.signal,
        [OFFLINE_REPLAY]: true,
      } as OfflineReplayConfig);
      queue.shift();
      persistQueue();
    } catch (error) {
      const cancelled = isCancelledError(error);
      // Logout cancellation and late results from an invalidated session are
      // intentional, not user-visible conflicts.
      if (generation === replayGeneration && !cancelled) {
        const payload = errorPayloadOf(error);
        const detail = payload?.data?.detail;
        const errorMsg =
          (typeof detail === 'string' && detail ? detail : undefined) ||
          errorMessageOf(error) ||
          'Request failed after reconnection';
        useOfflineStore.getState().addConflict(item.config, String(errorMsg), item.userId);
        queue.shift();
        persistQueue();
        // A server-side rejection (an HTTP status) is final for this item:
        // surface it as a conflict and keep replaying the rest of the queue.
        // A 401 means every remaining mutation shares the auth problem, so
        // stop there (the refresh/logout flow re-triggers a fresh flush).
        // Network-level failures mean the connection dropped again, so stop
        // and let the next flush trigger (online event, auth-ready) retry.
        const status = payload?.status;
        if (typeof status === 'number' && status !== 401) continue;
        return;
      }
      return;
    } finally {
      replayControllers.delete(controller);
    }
  }
}

function restorePersistedQueue(): void {
  if (queue.length > 0) return;
  queue.push(...readQueuedRequests());
}

function requestQueueFlush(): Promise<void> {
  if (activeFlush) {
    // An initial auth-ready flush can observe an empty queue while an offline
    // mutation is added immediately afterwards. Do not let the online event
    // return that already-completed flush and leave the new item stuck.
    if (queue.length === 0 || replayControllers.size > 0 || !getAuthState().user?.id) {
      return activeFlush;
    }
    const pendingFlush = activeFlush;
    return pendingFlush.then(async () => {
      if (queue.length > 0 && getAuthState().user?.id) await requestQueueFlush();
    });
  }
  const flush = flushQueue().finally(() => {
    if (activeFlush === flush) activeFlush = null;
  });
  activeFlush = flush;
  return flush;
}

function resumeOfflineQueue() {
  const userId = getAuthState().user?.id;
  if (userId) useOfflineStore.getState().discardForeignConflicts(userId);
  restorePersistedQueue();
  return requestQueueFlush();
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    offline = false;
    void requestQueueFlush();
  });
  window.addEventListener('offline', () => {
    offline = true;
  });
  window.addEventListener('aac:auth-ready', () => {
    void resumeOfflineQueue();
  });
  const clearSessionMutations = () => {
    // Queued mutations and replay conflicts belong to the previous session.
    // Never replay them after another user signs in on this browser.
    queue.length = 0;
    replayGeneration += 1;
    // Let a new authenticated session start its own replay even if an old
    // adapter ignores AbortSignal. The old flush observes the generation and
    // cannot mutate the new session's queue when it eventually settles.
    activeFlush = null;
    replayControllers.forEach((controller) => controller.abort());
    replayControllers.clear();
    clearOfflinePersistence();
    useOfflineStore.getState().clearConflicts();
  };
  window.addEventListener('aac:auth-logout', clearSessionMutations);
  window.addEventListener('aac:auth-context-changed', clearSessionMutations);
}

function currentUILanguage(): string {
  try {
    return localStorage.getItem('aac_assistant_locale') || 'es';
  } catch {
    return 'es';
  }
}

api.interceptors.request.use((config) => {
  const { token } = getAuthState();
  const headers = config.headers;
  const explicitAuthorization =
    typeof headers?.has === 'function'
      ? headers.has('Authorization')
      : headers?.Authorization !== undefined || headers?.authorization !== undefined;
  if (token && !explicitAuthorization) {
    const bearer = token;
    const requestHeaders = AxiosHeaders.from(config.headers ?? {});
    requestHeaders.set('Authorization', `Bearer ${bearer}`);
    config.headers = requestHeaders;
  }
  // Send the UI language to the backend so unauthenticated requests (login,
  // setup, register) and any error that precedes user-preference resolution
  // are answered in the user's language instead of the API default.
  if (!(config.headers instanceof AxiosHeaders)) {
    config.headers = AxiosHeaders.from(config.headers ?? {});
  }
  config.headers.set('Accept-Language', currentUILanguage());
  // Long-running operations (LLM generation, local speech-to-text) get a
  // larger client ceiling than the 30s default. Axios has already merged the
  // instance default into config.timeout by the time interceptors run, so an
  // override is applied only when the caller did not set an explicit
  // per-request timeout of their own.
  const longTimeout = resolveRequestTimeout(config.url);
  if (
    longTimeout !== undefined &&
    (config.timeout === undefined ||
      config.timeout === api.defaults.timeout ||
      !Number.isFinite(config.timeout))
  ) {
    config.timeout = longTimeout;
  }
  // If offline and non-GET, queue the request for retry. Authentication and
  // registration requests are never retained in browser storage or replayed.
  if (
    offline &&
    config.method &&
    config.method.toUpperCase() !== 'GET' &&
    !isOfflineExcludedEndpoint(config.url) &&
    !(config as OfflineReplayConfig)[OFFLINE_REPLAY]
  ) {
    // The original request may be cancelled while offline; replay must get a
    // fresh lifecycle and therefore cannot reuse its aborted signal.
    const userId = getAuthState().user?.id;
    if (queue.length >= MAX_OFFLINE_QUEUE_SIZE) {
      // Bound offline memory use and avoid an unbounded write burst after a
      // long outage. Record the rejected request in the existing conflict UI
      // so the user can retry or dismiss it explicitly.
      useOfflineStore.getState().addConflict(
        { ...config, signal: undefined },
        'Offline mutation queue is full',
        userId,
      );
      return Promise.reject({
        message: 'Offline mutation queue is full',
        code: 'ERR_OFFLINE_QUEUE_FULL',
      });
    }
    if (!userId) {
      return Promise.reject({ message: 'offline', code: 'ERR_OFFLINE' });
    }
    queue.push({
      config: removeAuthorizationHeader(config),
      userId,
    });
    persistQueue();
    // Throw a controlled error to let UI disable actions
    return Promise.reject({ message: 'offline', code: 'ERR_OFFLINE' });
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.config && !error.config.headers) {
      error.config.headers = new AxiosHeaders();
    }

    const status = error?.response?.status;
    const isOfflineReplay = Boolean(error.config?.[OFFLINE_REPLAY]);
    // Replay handles an unauthorized mutation as a visible conflict. Logging
    // out here would clear the queued mutation before that conflict can be
    // recorded, causing silent loss when an access token expired offline.
    if (status === 401 && !isAuthFlowEndpoint(error.config?.url) && !isOfflineReplay) {
      const alreadyRetried = Boolean(error.config?.[RETRIED_AFTER_REFRESH]);
      const { logout, refreshAccessToken } = getAuthState();
      if (!alreadyRetried && refreshAccessToken && accessTokenIsExpired(getAuthState().token ?? null)) {
        try {
          // The refresh token outlives the access token (7 days vs 2 hours);
          // silently extending the session keeps long-running users logged in
          // instead of bouncing them to the login screen mid-use.
          const refreshed = await refreshAccessToken();
          if (refreshed) {
            // Retry the original request once with the fresh token. The
            // request interceptor only attaches a stored token when no
            // Authorization header is present, so strip the expired one
            // from the retried config before re-issuing.
            const retryConfig: RefreshRetryConfig = {
              ...error.config,
              [RETRIED_AFTER_REFRESH]: true,
            };
            if (retryConfig.headers) {
              delete retryConfig.headers.Authorization;
              delete retryConfig.headers.authorization;
            }
            return api.request(retryConfig);
          }
        } catch {
          // Fall through to the logout path when refresh fails.
        }
      }
      try {
        logout?.();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
      } catch {
        // Logout and redirect are best-effort during an invalid session.
      }
    }
    return Promise.reject(error);
  }
);

export default api;
export const apiOffline = {
  isOffline: () => offline,
  resumeQueue: resumeOfflineQueue,
};
