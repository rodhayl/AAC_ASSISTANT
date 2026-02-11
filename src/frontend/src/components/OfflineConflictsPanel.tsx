import { AlertTriangle, RefreshCw, X } from 'lucide-react'
import { useOfflineStore } from '../store/offlineStore'
import api from '../lib/api'
import { formatTime } from '../lib/format'

export function OfflineConflictsPanel() {
  const { conflicts, removeConflict, clearConflicts, incrementRetry } = useOfflineStore()

  if (conflicts.length === 0) return null

  const handleRetry = async (conflictId: string) => {
    const conflict = conflicts.find(c => c.id === conflictId)
    if (!conflict) return

    incrementRetry(conflictId)

    try {
      await api.request(conflict.config)
      removeConflict(conflictId)
    } catch (error: unknown) {
      console.error('Retry failed:', error)
    }
  }

  const handleDismiss = (conflictId: string) => {
    removeConflict(conflictId)
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 max-w-full">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl border border-red-200 dark:border-red-800 overflow-hidden">
        <div className="bg-red-50 dark:bg-red-900/30 px-4 py-3 border-b border-red-200 dark:border-red-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
            <h3 className="font-semibold text-red-900 dark:text-red-200">
              Offline Conflicts ({conflicts.length})
            </h3>
          </div>
          <button
            onClick={clearConflicts}
            className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-200"
            aria-label="Clear all conflicts"
            title="Dismiss all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="max-h-96 overflow-y-auto">
          {conflicts.map(conflict => (
            <div
              key={conflict.id}
              className="p-4 border-b border-gray-200 dark:border-gray-700 last:border-b-0"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {conflict.config.method?.toUpperCase()} {conflict.config.url}
                  </div>
                  <div className="text-xs text-red-600 dark:text-red-400 mt-1">
                    {conflict.error}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {formatTime(conflict.timestamp)}
                    {conflict.retryCount > 0 && (
                      <span className="ml-2">
                        • Retries: {conflict.retryCount}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex gap-1 flex-shrink-0">
                  <button
                    onClick={() => handleRetry(conflict.id)}
                    className="p-2 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded"
                    aria-label="Retry request"
                    title="Retry"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDismiss(conflict.id)}
                    className="p-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                    aria-label="Dismiss conflict"
                    title="Dismiss"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="bg-gray-50 dark:bg-gray-900 px-4 py-2 text-xs text-gray-600 dark:text-gray-400">
          These requests failed after coming back online. You can retry or dismiss them.
        </div>
      </div>
    </div>
  )
}
