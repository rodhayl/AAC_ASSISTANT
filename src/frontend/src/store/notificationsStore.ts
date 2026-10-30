import { create } from 'zustand'
import api from '../lib/api'

export interface NotificationItem {
  id: string | number
  title: string
  message: string
  read: boolean
  createdAt: number
  type?: string
}

interface NotificationsState {
  items: NotificationItem[]
  loading: boolean
  loaded: boolean
  add: (n: Omit<NotificationItem, 'id' | 'read' | 'createdAt'>) => void
  markAsRead: (id: string | number, sync?: boolean) => Promise<void>
  markAllAsRead: (sync?: boolean) => Promise<void>
  unreadCount: () => number
  loadFromBackend: (userId: number) => Promise<void>
  setItems: (items: NotificationItem[]) => void
}

export const useNotificationsStore = create<NotificationsState>((set, get) => ({
  items: [],
  loading: false,
  loaded: false,

  add: (n) => {
    const id = Math.random().toString(36).slice(2)
    const item: NotificationItem = { id, title: n.title, message: n.message, read: false, createdAt: Date.now(), type: n.type }
    set({ items: [item, ...get().items] })
  },

  markAsRead: async (id, sync = true) => {
    // Update local state immediately
    set({ items: get().items.map(i => i.id === id ? { ...i, read: true } : i) })

    // Sync to backend if requested and id is numeric (from backend)
    if (sync && typeof id === 'number') {
      try {
        // Backend uses JWT auth to identify user - no need to send user_id
        await api.put(`/notifications/${id}/read`)
      } catch (error) {
        console.error('Failed to sync read state:', error)
      }
    }
  },

  markAllAsRead: async (sync = true) => {
    // Update local state immediately
    set({ items: get().items.map(i => ({ ...i, read: true })) })

    // Sync to backend if requested
    if (sync) {
      try {
        // Backend uses JWT auth to identify user - no need to send user_id
        await api.put('/notifications/read-all')
      } catch (error) {
        console.error('Failed to sync read-all state:', error)
      }
    }
  },

  unreadCount: () => get().items.filter(i => !i.read).length,

  loadFromBackend: async (userId: number) => {
    if (get().loaded) return // Only load once
    set({ loading: true })
    try {
      const response = await api.get('/notifications', {
        params: { user_id: userId, limit: 50 }
      })
      const { notifications } = response.data

      // Convert backend format to store format
      const items: NotificationItem[] = notifications.map((n: { id: string; title: string; message: string; is_read: boolean; created_at: string; type?: NotificationItem['type'] }) => ({
        id: n.id,
        title: n.title,
        message: n.message,
        read: n.is_read,
        createdAt: new Date(n.created_at).getTime(),
        type: n.type,
      }))

      set({ items, loaded: true })
    } catch (error) {
      console.error('Failed to load notifications from backend:', error)
    } finally {
      set({ loading: false })
    }
  },

  setItems: (items) => {
    set({ items })
  },
}))
