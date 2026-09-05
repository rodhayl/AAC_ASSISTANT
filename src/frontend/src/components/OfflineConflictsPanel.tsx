import { AlertTriangle, RefreshCw, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useOfflineStore } from '../store/offlineStore'
import api, { apiOffline } from '../lib/api'
import { formatTime } from '../lib/format'
import { IconButton } from './ui/icon-button'
import { StatusMessage } from './ui/StatusMessage'

export function OfflineConflictsPanel() {
  const { t } = useTranslation('common');
  const conflicts = useOfflineStore((state) => state.conflicts)
  const removeConflict = useOfflineStore((state) => state.removeConflict)
  const clearConflicts = useOfflineStore((state) => state.clearConflicts)
  const incrementRetry = useOfflineStore((state) => state.incrementRetry)

  if (conflicts.length === 0) return null

  const handleRetry = async (conflictId: string) => {
    const conflict = conflicts.find(c => c.id === conflictId)
    if (!conflict) return

    if (apiOffline.isOffline()) {
      return
    }

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
      <div className="bg-surface rounded-lg shadow-2xl border border-red-200 dark:border-red-800 overflow-hidden">
        <div className="bg-red-50 dark:bg-red-900/30 px-4 py-3 border-b border-red-200 dark:border-red-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
            <h3 className="font-semibold text-red-900 dark:text-red-200">
              {t('offline.title', { count: conflicts.length })}
            </h3>
          </div>
          <IconButton
            label={t('offline.clearAll')}
            onClick={() => clearConflicts()}
            className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-200"
          >
            <X className="w-5 h-5" />
          </IconButton>
        </div>

        <div className="max-h-96 overflow-y-auto">
          {conflicts.map(conflict => (
            <div
              key={conflict.id}
              className="p-4 border-b border-border last:border-b-0"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-foreground">
                    {conflict.config.method?.toUpperCase()} {conflict.config.url}
                  </div>
                  <StatusMessage variant="error" className="border-0 bg-transparent p-0 text-xs mt-1">
                    {conflict.error}
                  </StatusMessage>
                  <div className="text-xs text-muted-foreground mt-1">
                    {formatTime(conflict.timestamp)}
                    {conflict.retryCount > 0 && (
                      <span className="ml-2">
                        • {t('offline.retries', { count: conflict.retryCount })}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex gap-1 flex-shrink-0">
                  <IconButton
                    label={t('offline.retry')}
                    onClick={() => handleRetry(conflict.id)}
                    className="p-2 text-brand hover:bg-brand/20 rounded"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </IconButton>
                  <IconButton
                    label={t('offline.dismiss')}
                    onClick={() => handleDismiss(conflict.id)}
                    className="p-2 text-muted-foreground hover:bg-surface-hover rounded"
                  >
                    <X className="w-4 h-4" />
                  </IconButton>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="bg-muted px-4 py-2 text-xs text-muted-foreground">
          {t('offline.conflictsHint')}
        </div>
      </div>
    </div>
  )
}
