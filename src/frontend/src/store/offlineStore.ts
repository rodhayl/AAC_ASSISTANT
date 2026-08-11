import { create } from 'zustand'
import type { AxiosRequestConfig } from 'axios'

export interface OfflineConflict {
  id: string
  config: AxiosRequestConfig
  error: string
  timestamp: number
  retryCount: number
}

interface OfflineState {
  conflicts: OfflineConflict[]
  addConflict: (config: AxiosRequestConfig, error: string) => void
  removeConflict: (id: string) => void
  clearConflicts: () => void
  incrementRetry: (id: string) => void
}

function isSafeJson(value: unknown, seen = new WeakSet<object>()): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value !== 'object') return typeof value !== 'function' && typeof value !== 'symbol';
  if (seen.has(value)) return false;
  seen.add(value);
  if (Array.isArray(value)) return value.every((item) => isSafeJson(item, seen));
  if (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) {
    return false;
  }
  return Object.values(value).every((item) => isSafeJson(item, seen));
}

function conflictRequestKey(config: AxiosRequestConfig): string | null {
  if (!isSafeJson(config.params) || !isSafeJson(config.data)) return null;
  try {
    return JSON.stringify({
      method: config.method?.toUpperCase(),
      url: config.url,
      params: config.params,
      data: config.data,
    });
  } catch {
    return null;
  }
}

export const useOfflineStore = create<OfflineState>((set, get) => ({
  conflicts: [],

  addConflict: (config, error) => {
    const requestKey = conflictRequestKey(config);
    if (
      requestKey !== null &&
      get().conflicts.some((conflict) => conflictRequestKey(conflict.config) === requestKey)
    ) {
      return;
    }
    const id = `conflict_${Date.now()}_${Math.random().toString(36).slice(2)}`
    const conflict: OfflineConflict = {
      id,
      config,
      error,
      timestamp: Date.now(),
      retryCount: 0,
    }
    set({ conflicts: [...get().conflicts, conflict] })
  },

  removeConflict: (id) => {
    set({ conflicts: get().conflicts.filter(c => c.id !== id) })
  },

  clearConflicts: () => {
    set({ conflicts: [] })
  },

  incrementRetry: (id) => {
    set({
      conflicts: get().conflicts.map(c =>
        c.id === id ? { ...c, retryCount: c.retryCount + 1 } : c
      )
    })
  },
}))
