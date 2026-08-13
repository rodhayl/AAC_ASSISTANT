import type { AxiosRequestConfig } from 'axios'

const QUEUE_STORAGE_KEY = 'aac-assistant-offline-queue-v1'
const CONFLICT_STORAGE_KEY = 'aac-assistant-offline-conflicts-v1'
const MAX_PERSISTED_ITEMS = 100
const MAX_PERSISTED_BYTES = 200_000
const PERSISTED_METHODS = new Set(['post', 'put', 'patch', 'delete'])
let persistenceDisabled = false

export interface PersistedOfflineQueueItem {
  userId: number
  config: AxiosRequestConfig
}

export interface PersistedOfflineConflict {
  id: string
  userId: number
  config: AxiosRequestConfig
  error: string
  timestamp: number
  retryCount: number
}

function getStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export function isPersistableJson(value: unknown, seen = new WeakSet<object>()): boolean {
  if (value === null || value === undefined) return true
  if (typeof value !== 'object') {
    return typeof value !== 'function' && typeof value !== 'symbol'
  }
  if (seen.has(value)) return false
  seen.add(value)
  if (Array.isArray(value)) return value.every((item) => isPersistableJson(item, seen))
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) return false
  return Object.values(value).every((item) => isPersistableJson(item, seen))
}

function sanitizeHeaders(headers: AxiosRequestConfig['headers']): Record<string, string> {
  let source: Record<string, unknown> = {}
  if (headers && typeof headers === 'object') {
    const candidate = headers as Record<string, unknown> & {
      toJSON?: () => Record<string, unknown>
    }
    source = typeof candidate.toJSON === 'function' ? candidate.toJSON() : candidate
  }

  return Object.entries(source).reduce<Record<string, string>>((result, [key, value]) => {
    if (key.toLowerCase() === 'authorization') return result
    if (typeof value === 'string') result[key] = value
    return result
  }, {})
}

export function removeAuthorizationHeader(config: AxiosRequestConfig): AxiosRequestConfig {
  return {
    ...config,
    signal: undefined,
    headers: sanitizeHeaders(config.headers),
  }
}

export function sanitizeOfflineConfig(config: AxiosRequestConfig): AxiosRequestConfig | null {
  if (!isPersistableJson(config.params) || !isPersistableJson(config.data)) return null
  return {
    method: config.method,
    url: config.url,
    baseURL: config.baseURL,
    params: config.params,
    data: config.data,
    headers: sanitizeHeaders(config.headers),
  }
}

function readList<T>(key: string, validate: (value: unknown) => T | null): T[] {
  if (persistenceDisabled) return []
  const storage = getStorage()
  if (!storage) return []
  try {
    const raw = storage.getItem(key)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      storage.removeItem(key)
      return []
    }
    const bounded = parsed.slice(0, MAX_PERSISTED_ITEMS)
    const validated = bounded
      .map(validate)
      .filter((item): item is T => item !== null)
    if (validated.length !== bounded.length || parsed.length > MAX_PERSISTED_ITEMS) {
      writeList(key, validated)
    }
    return validated
  } catch {
    try {
      storage.removeItem(key)
    } catch {
      // Corrupt storage is not allowed to break application startup.
    }
    return []
  }
}

function serializedByteLength(payload: string): number {
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(payload).byteLength
  }
  // TextEncoder is available in supported browsers; this fallback keeps the
  // helper safe in older test/runtime environments.
  return encodeURIComponent(payload).replace(/%[0-9A-F]{2}|./g, 'x').length
}

function writeList(key: string, items: unknown[]): number {
  if (persistenceDisabled) return -1
  const storage = getStorage()
  if (!storage) {
    persistenceDisabled = true
    return -1
  }
  try {
    const boundedItems = items.slice(0, MAX_PERSISTED_ITEMS)
    while (boundedItems.length > 0) {
      const payload = JSON.stringify(boundedItems)
      if (serializedByteLength(payload) <= MAX_PERSISTED_BYTES) {
        // Do not remove the previous value before setItem succeeds. A quota
        // failure must not destroy the last durable queue snapshot.
        storage.setItem(key, payload)
        return boundedItems.length
      }
      // Preserve the FIFO prefix that fits instead of dropping every valid
      // mutation because one later item is unusually large.
      boundedItems.pop()
    }
    storage.removeItem(key)
    return 0
  } catch {
    persistenceDisabled = true
    // Remove a stale snapshot when a write fails; otherwise a successfully
    // replayed item could be replayed again from the old value after reload.
    try {
      storage.removeItem(key)
    } catch {
      // Private browsing may reject cleanup as well.
    }
    return -1
  }
}

function validateQueueItem(value: unknown): PersistedOfflineQueueItem | null {
  if (!value || typeof value !== 'object') return null
  const item = value as { userId?: unknown; config?: unknown }
  if (typeof item.userId !== 'number' || !Number.isInteger(item.userId) || item.userId < 1) {
    return null
  }
  if (!item.config || typeof item.config !== 'object') return null
  const rawConfig = item.config as AxiosRequestConfig
  if (
    typeof rawConfig.url !== 'string' ||
    !rawConfig.url ||
    typeof rawConfig.method !== 'string' ||
    !PERSISTED_METHODS.has(rawConfig.method.toLowerCase())
  ) {
    return null
  }
  const config = sanitizeOfflineConfig(rawConfig)
  return config ? { userId: item.userId, config } : null
}

function validateConflict(value: unknown): PersistedOfflineConflict | null {
  if (!value || typeof value !== 'object') return null
  const item = value as Partial<PersistedOfflineConflict>
  if (
    typeof item.id !== 'string' ||
    typeof item.userId !== 'number' ||
    !Number.isInteger(item.userId) ||
    item.userId < 1 ||
    typeof item.error !== 'string' ||
    typeof item.timestamp !== 'number' ||
    typeof item.retryCount !== 'number' ||
    !item.config ||
    typeof item.config !== 'object'
  ) {
    return null
  }
  const rawConfig = item.config
  if (
    typeof rawConfig.url !== 'string' ||
    !rawConfig.url ||
    typeof rawConfig.method !== 'string' ||
    !PERSISTED_METHODS.has(rawConfig.method.toLowerCase())
  ) {
    return null
  }
  const config = sanitizeOfflineConfig(rawConfig)
  return config
    ? {
        id: item.id,
        userId: item.userId,
        config,
        error: item.error,
        timestamp: item.timestamp,
        retryCount: item.retryCount,
      }
    : null
}

export function readOfflineQueue(): PersistedOfflineQueueItem[] {
  return readList(QUEUE_STORAGE_KEY, validateQueueItem)
}

export function writeOfflineQueue(items: PersistedOfflineQueueItem[]): number {
  return writeList(QUEUE_STORAGE_KEY, items)
}

export function readOfflineConflicts(): PersistedOfflineConflict[] {
  return readList(CONFLICT_STORAGE_KEY, validateConflict)
}

export function writeOfflineConflicts(items: PersistedOfflineConflict[]): number {
  return writeList(CONFLICT_STORAGE_KEY, items)
}

export function clearOfflinePersistence(): void {
  const storage = getStorage()
  if (!storage) return
  try {
    storage.removeItem(QUEUE_STORAGE_KEY)
    storage.removeItem(CONFLICT_STORAGE_KEY)
    persistenceDisabled = false
  } catch {
    // Storage cleanup is best effort. Keep persistence disabled if cleanup
    // failed, because an old snapshot may still be present.
  }
}
