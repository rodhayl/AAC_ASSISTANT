import axios from 'axios';
import type { AxiosRequestConfig } from 'axios';
import { getAuthState } from './authState';
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

type ApiError = {
  message?: unknown;
  response?: {
    data?: {
      detail?: unknown;
      error?: unknown;
      message?: unknown;
    };
  };
};

export function extractError(error: unknown, fallback: string): string {
  const apiError = error as ApiError;
  const detail = apiError?.response?.data?.detail;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((entry: unknown) => {
        if (
          entry &&
          typeof entry === 'object' &&
          'msg' in entry &&
          typeof (entry as { msg?: unknown }).msg === 'string'
        ) {
          return (entry as { msg: string }).msg;
        }
        return String(entry);
      })
      .join(', ');
  }

  if (typeof detail === 'object' && detail !== null) {
    return JSON.stringify(detail);
  }

  const responseError = apiError?.response?.data?.error;
  if (typeof responseError === 'string' && responseError) return responseError;

  const responseMessage = apiError?.response?.data?.message;
  if (typeof responseMessage === 'string' && responseMessage) return responseMessage;

  return typeof apiError?.message === 'string' && apiError.message ? apiError.message : fallback;
}

const api = axios.create({
  baseURL: config.API_BASE_URL,
  timeout: 30000, // 30 seconds timeout
});

const AUTH_FLOW_ENDPOINTS = new Set([
  '/auth/token',
  '/auth/refresh',
  '/auth/change-password',
  '/auth/logout',
]);

const OFFLINE_EXCLUDED_ENDPOINTS = new Set([
  ...AUTH_FLOW_ENDPOINTS,
  '/auth/register',
  '/auth/login',
  '/auth/logout',
]);

export function isAuthFlowEndpoint(url?: string): boolean {
  if (!url) return false;

  try {
    const pathname = new URL(url, 'http://localhost').pathname
      .replace(/^\/api(?=\/)/, '');
    return AUTH_FLOW_ENDPOINTS.has(pathname);
  } catch {
    return false;
  }
}

function isOfflineExcludedEndpoint(url?: string): boolean {
  if (!url) return false;

  try {
    const pathname = new URL(url, 'http://localhost').pathname
      .replace(/^\/api(?=\/)/, '');
    return OFFLINE_EXCLUDED_ENDPOINTS.has(pathname);
  } catch {
    return false;
  }
}

let offline = typeof navigator !== 'undefined' ? !navigator.onLine : false;
const MAX_OFFLINE_QUEUE_SIZE = 100;
const OFFLINE_REPLAY: unique symbol = Symbol('offline-replay');
type OfflineReplayConfig = AxiosRequestConfig & { [OFFLINE_REPLAY]?: true };
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
      const replayError = error as ApiError & { code?: unknown; name?: unknown };
      const cancelled =
        replayError.code === 'ERR_CANCELED' || replayError.name === 'CanceledError';
      // Logout cancellation and late results from an invalidated session are
      // intentional, not user-visible conflicts.
      if (generation === replayGeneration && !cancelled) {
        const errorMsg =
          replayError.response?.data?.detail ||
          replayError.message ||
          'Request failed after reconnection';
        useOfflineStore.getState().addConflict(item.config, String(errorMsg), item.userId);
        queue.shift();
        persistQueue();
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
  if (activeFlush) return activeFlush;
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

api.interceptors.request.use((config) => {
  const { token } = getAuthState();
  const headers = config.headers;
  const explicitAuthorization =
    typeof headers?.has === 'function'
      ? headers.has('Authorization')
      : headers?.Authorization !== undefined || headers?.authorization !== undefined;
  if (token && !explicitAuthorization) {
    const bearer = token;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config.headers = { ...config.headers, Authorization: `Bearer ${bearer}` } as any;
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
  (error) => {
    if (error.config && !error.config.headers) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      error.config.headers = {} as any;
    }

    const status = error?.response?.status;
    const isOfflineReplay = Boolean(error.config?.[OFFLINE_REPLAY]);
    // Replay handles an unauthorized mutation as a visible conflict. Logging
    // out here would clear the queued mutation before that conflict can be
    // recorded, causing silent loss when an access token expired offline.
    if (status === 401 && !isAuthFlowEndpoint(error.config?.url) && !isOfflineReplay) {
      try {
        const { logout } = getAuthState();
        logout?.();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
      } catch { /* ignore logout errors during redirect */ }
    }
    return Promise.reject(error);
  }
);

export default api;
export const apiOffline = {
  isOffline: () => offline,
  resumeQueue: resumeOfflineQueue,
};
