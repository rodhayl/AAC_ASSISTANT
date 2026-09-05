import { useNotificationsStore } from '../store/notificationsStore'
import { useTranslation } from 'react-i18next'
import { localizeAchievementMessage } from '../lib/achievementLocalization'

export function NotificationsPanel({ onClose }: { onClose: () => void }) {
  const items = useNotificationsStore((state) => state.items)
  const markAsRead = useNotificationsStore((state) => state.markAsRead)
  const markAllAsRead = useNotificationsStore((state) => state.markAllAsRead)
  const { t } = useTranslation('common')

  // Backend achievement notifications store the canonical English name (e.g.
  // "First Steps (+10 pts)"); localize the known system names so Spanish users
  // see their language instead of the raw catalog text.
  const displayTitle = (n: { title?: string | null; type?: string | null }) => {
    if (n.type === 'achievement') {
      return t('notifications.achievementUnlocked', n.title || t('notifications.defaultTitle'))
    }
    return n.title || t('notifications.defaultTitle')
  }

  const displayMessage = (n: { message?: string | null; type?: string | null }) => {
    const message = n.message || t('notifications.defaultMessage')
    if (n.type === 'achievement') {
      return localizeAchievementMessage(message, t)
    }
    return message
  }
  return (
    <div className="absolute right-6 top-16 w-80 bg-surface border border-border rounded-xl shadow-lg z-50" aria-live="polite">
      <div className="p-3 flex justify-between items-center border-b border-border">
        <span className="text-sm font-medium text-foreground">{t('notifications.title')}</span>
        <button onClick={() => markAllAsRead()} className="text-xs text-brand hover:text-brand/80">{t('notifications.markAll')}</button>
      </div>
      <div className="max-h-96 overflow-auto">
        {items.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground">{t('notifications.empty')}</div>
        ) : items.map(n => (
          <button key={n.id} onClick={() => markAsRead(n.id)} className={`w-full text-left p-3 flex flex-col gap-1 border-b border-border hover:bg-surface-hover transition-colors ${n.read ? 'bg-surface' : 'bg-brand/10'}`}>
            <span className="text-sm font-medium text-foreground">{displayTitle(n)}</span>
            <span className="text-sm text-foreground leading-relaxed">{displayMessage(n)}</span>
            {n.type && (
              <span className="text-xs text-muted-foreground mt-1 capitalize">{n.type}</span>
            )}
          </button>
        ))}
      </div>
      <div className="p-3 border-t border-border flex justify-end">
        <button onClick={onClose} className="text-sm text-foreground hover:bg-surface-hover px-3 py-1 rounded-lg">{t('notifications.close')}</button>
      </div>
    </div>
  )
}
