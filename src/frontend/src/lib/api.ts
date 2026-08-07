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
const queue: Array<AxiosRequestConfig> = []

function flushQueue() {
  if (queue.length === 0) return
  const items = queue.splice(0)
  for (const cfg of items) {
    api.request(cfg).catch((error) => {
      // Track conflicts that fail on replay
      const errorMsg = error?.response?.data?.detail || error?.message || 'Request failed after reconnection'
      useOfflineStore.getState().addConflict(cfg, errorMsg)
    })
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    offline = false
    flushQueue()
  })
  window.addEventListener('offline', () => {
    offline = true
  })
}

api.interceptors.request.use((config) => {
  const { token } = useAuthStore.getState();
  if (token) {
    const bearer = token;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config.headers = { ...config.headers, Authorization: `Bearer ${bearer}` } as any;
  }
  // If offline and non-GET, queue the request for retry
  if (offline && config.method && config.method.toUpperCase() !== 'GET') {
    queue.push({ ...config })
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
