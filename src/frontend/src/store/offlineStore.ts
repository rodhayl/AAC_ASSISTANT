import { create } from 'zustand'
import type { AxiosRequestConfig } from 'axios'
import {
  isPersistableJson,
  readOfflineConflicts,
  removeAuthorizationHeader,
  sanitizeOfflineConfig,
  writeOfflineConflicts,
} from '../lib/offlinePersistence'

export interface OfflineConflict {
  id: string
  userId?: number
  config: AxiosRequestConfig
  error: string
  timestamp: number
  retryCount: number
}

// Cap on retained conflicts (G1): the store persists every entry to
// localStorage, so an unbounded list from a long offline session would grow the
// stored JSON without limit. Newest entries win.
export const MAX_STORED_CONFLICTS = 50

interface OfflineState {
  conflicts: OfflineConflict[]
  addConflict: (config: AxiosRequestConfig, error: string, userId?: number) => void
  removeConflict: (id: string) => void
  clearConflicts: () => void
  discardForeignConflicts: (userId: number) => void
  incrementRetry: (id: string) => void
  updateConflictError: (id: string, error: string) => void
}

function conflictRequestKey(config: AxiosRequestConfig): string | null {
  if (!isPersistableJson(config.params) || !isPersistableJson(config.data)) return null
  try {
    return JSON.stringify({
      method: config.method?.toUpperCase(),
      url: config.url,
      params: config.params,
      data: config.data,
    })
  } catch {
    return null
  }
}

function persistConflicts(conflicts: OfflineConflict[]): void {
  writeOfflineConflicts(
    conflicts.flatMap((conflict) => {
      if (conflict.userId === undefined) return []
      const config = sanitizeOfflineConfig(conflict.config)
      return config ? [{ ...conflict, config, userId: conflict.userId }] : []
    }),
  )
}

export const useOfflineStore = create<OfflineState>((set, get) => ({
  conflicts: readOfflineConflicts(),

  addConflict: (config, error, userId) => {
    const requestKey = conflictRequestKey(config)
    if (
      requestKey !== null &&
      get().conflicts.some((conflict) => conflictRequestKey(conflict.config) === requestKey)
    ) {
      return
    }
    const conflict: OfflineConflict = {
      id: `conflict_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      userId,
      config: removeAuthorizationHeader(config),
      error,
      timestamp: Date.now(),
      retryCount: 0,
    }
    const conflicts = [...get().conflicts, conflict].slice(-MAX_STORED_CONFLICTS)
    set({ conflicts })
    persistConflicts(conflicts)
  },

  removeConflict: (id) => {
    const conflicts = get().conflicts.filter((conflict) => conflict.id !== id)
    set({ conflicts })
    persistConflicts(conflicts)
  },

  clearConflicts: () => {
    set({ conflicts: [] })
    persistConflicts([])
  },

  discardForeignConflicts: (userId) => {
    const conflicts = get().conflicts.filter((conflict) => conflict.userId === userId)
    if (conflicts.length !== get().conflicts.length) {
      set({ conflicts })
      persistConflicts(conflicts)
    }
  },

  incrementRetry: (id) => {
    const conflicts = get().conflicts.map((conflict) =>
      conflict.id === id
        ? { ...conflict, retryCount: conflict.retryCount + 1 }
        : conflict,
    )
    set({ conflicts })
    persistConflicts(conflicts)
  },

  updateConflictError: (id, error) => {
    // A manual retry that fails must say so on the conflict itself; a
    // console-only failure left the entry looking untouched (A6).
    const conflicts = get().conflicts.map((conflict) =>
      conflict.id === id ? { ...conflict, error, timestamp: Date.now() } : conflict,
    )
    set({ conflicts })
    persistConflicts(conflicts)
  },
}))
