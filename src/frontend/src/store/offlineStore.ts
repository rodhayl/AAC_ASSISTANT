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

export const useOfflineStore = create<OfflineState>((set, get) => ({
  conflicts: [],

  addConflict: (config, error) => {
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
