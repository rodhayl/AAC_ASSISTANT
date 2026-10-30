import axios from 'axios';
import type { AxiosRequestConfig } from 'axios';
import { useAuthStore } from '../store/authStore';
import { config } from '../config';
import { useOfflineStore } from '../store/offlineStore';

const api = axios.create({
  baseURL: config.API_BASE_URL,
  timeout: 30000, // 30 seconds timeout
});

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
    if (status === 401) {
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
