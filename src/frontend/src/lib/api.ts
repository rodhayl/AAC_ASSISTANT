import axios from 'axios';
import type { AxiosRequestConfig } from 'axios';
import { useAuthStore } from '../store/authStore';
import { config } from '../config';
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

let offline = typeof navigator !== 'undefined' ? !navigator.onLine : false
const MAX_OFFLINE_QUEUE_SIZE = 100
const queue: Array<AxiosRequestConfig> = []
const replayControllers = new Set<AbortController>()
let replayGeneration = 0

async function flushQueue() {
  if (queue.length === 0) return
  const items = queue.splice(0)
  const generation = replayGeneration

  // Replay in FIFO order rather than launching an outage-sized write burst.
  // The queue is deliberately small and mutations may depend on earlier IDs.
  for (const cfg of items) {
    if (generation !== replayGeneration) return

    const controller = new AbortController()
    replayControllers.add(controller)
    try {
      await api.request({ ...cfg, signal: controller.signal })
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
        useOfflineStore.getState().addConflict(cfg, String(errorMsg));
        // Preserve dependent mutations for explicit conflict resolution rather
        // than replaying them after a prerequisite failed.
        queue.unshift(...items.slice(items.indexOf(cfg) + 1));
        return;
      }
    } finally {
      replayControllers.delete(controller)
    }
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    offline = false
    void flushQueue()
  })
  window.addEventListener('offline', () => {
    offline = true
  })
  const clearSessionMutations = () => {
    // Queued mutations and replay conflicts belong to the previous session.
    // Never replay them after another user signs in on this browser.
    queue.length = 0
    replayGeneration += 1
    replayControllers.forEach((controller) => controller.abort())
    replayControllers.clear()
    useOfflineStore.getState().clearConflicts()
  }
  window.addEventListener('aac:auth-logout', clearSessionMutations)
  window.addEventListener('aac:auth-context-changed', clearSessionMutations)
}

api.interceptors.request.use((config) => {
  const { token } = useAuthStore.getState();
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
  // If offline and non-GET, queue the request for retry
  if (
    offline &&
    config.method &&
    config.method.toUpperCase() !== 'GET' &&
    !isAuthFlowEndpoint(config.url)
  ) {
    // The original request may be cancelled while offline; replay must get a
    // fresh lifecycle and therefore cannot reuse its aborted signal.
    if (queue.length >= MAX_OFFLINE_QUEUE_SIZE) {
      // Bound offline memory use and avoid an unbounded write burst after a
      // long outage. Record the rejected request in the existing conflict UI
      // so the user can retry or dismiss it explicitly.
      useOfflineStore.getState().addConflict(
        { ...config, signal: undefined },
        'Offline mutation queue is full',
      )
      return Promise.reject({
        message: 'Offline mutation queue is full',
        code: 'ERR_OFFLINE_QUEUE_FULL',
      })
    }
    queue.push({ ...config, signal: undefined })
    // Throw a controlled error to let UI disable actions
    return Promise.reject({ message: 'offline', code: 'ERR_OFFLINE' })
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
    if (status === 401 && !isAuthFlowEndpoint(error.config?.url)) {
      try {
        const { logout } = useAuthStore.getState();
        logout();
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
};
