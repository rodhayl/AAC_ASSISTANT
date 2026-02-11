import { useNotificationsStore } from '../store/notificationsStore'
import { useTranslation } from 'react-i18next'

export function NotificationsPanel({ onClose }: { onClose: () => void }) {
  const { items, markAsRead, markAllAsRead } = useNotificationsStore()
  const { t } = useTranslation('common')
  return (
    <div className="absolute right-6 top-16 w-80 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50" aria-live="polite">
      <div className="p-3 flex justify-between items-center border-b border-gray-200 dark:border-gray-700">
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{t('notifications.title')}</span>
        <button onClick={() => markAllAsRead()} className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300">{t('notifications.markAll')}</button>
      </div>
      <div className="max-h-96 overflow-auto">
        {items.length === 0 ? (
          <div className="p-4 text-sm text-gray-500 dark:text-gray-400">{t('notifications.empty')}</div>
        ) : items.map(n => (
          <button key={n.id} onClick={() => markAsRead(n.id)} className={`w-full text-left p-3 flex flex-col gap-1 border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${n.read ? 'bg-white dark:bg-gray-800' : 'bg-indigo-50 dark:bg-indigo-900/30'}`}>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{n.title || t('notifications.defaultTitle')}</span>
            <span className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{n.message || t('notifications.defaultMessage')}</span>
            {n.type && (
              <span className="text-xs text-gray-500 dark:text-gray-400 mt-1 capitalize">{n.type}</span>
            )}
          </button>
        ))}
      </div>
      <div className="p-3 border-t border-gray-200 dark:border-gray-700 flex justify-end">
        <button onClick={onClose} className="text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 px-3 py-1 rounded-lg">{t('notifications.close')}</button>
      </div>
    </div>
  )
}
