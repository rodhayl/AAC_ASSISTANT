import { Bell, User, BookOpen, Menu, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useNotificationsStore } from '../store/notificationsStore';
import { NotificationsPanel } from './NotificationsPanel';
import { config } from '../config';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';

interface NavbarProps {
  onMenuToggle?: () => void;
  isSidebarOpen?: boolean;
}

export function Navbar({ onMenuToggle, isSidebarOpen = false }: NavbarProps) {
  const { user } = useAuthStore();
  const [open, setOpen] = useState(false);
  const unread = useNotificationsStore(state => state.unreadCount());
  const loadFromBackend = useNotificationsStore(state => state.loadFromBackend);
  const { t } = useTranslation('common');

  // Load persisted notifications from backend on mount
  useEffect(() => {
    if (user?.id) {
      loadFromBackend(user.id);
    }
  }, [user?.id, loadFromBackend]);

  useEffect(() => {
    // Only connect when authenticated; pass token for validation
    if (!user?.id || !useAuthStore.getState().token) return;
    const token = useAuthStore.getState().token;
    let es: EventSource | null = null;
    try {
      es = new EventSource(`${config.API_BASE_URL}/notifications/stream?token=${encodeURIComponent(token || '')}`);
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data || '{}');
          if (data?.title && data?.message) {
            useNotificationsStore.getState().add({ title: data.title, message: data.message, type: data.type || 'info' });
          }
        } catch {
          /* ignore parse errors */
        }
      };
    } catch {
      /* ignore SSE connection errors */
    }
    return () => {
      try {
        es?.close();
      } catch {
        /* ignore */
      }
    };
  }, [user?.id])

  return (
    <header className="h-16 bg-surface/90 dark:bg-transparent backdrop-blur-sm border-b border-border dark:border-white/5 flex items-center justify-between gap-2 px-4 md:px-6 transition-all duration-200 z-10 sticky top-0">
      <div className="flex items-center gap-3 min-w-0">
        {onMenuToggle && (
          <button
            type="button"
            onClick={onMenuToggle}
            aria-label={t('navbar.toggleMenu', { defaultValue: 'Toggle menu' })}
            aria-expanded={isSidebarOpen}
            className="md:hidden rounded-lg p-2 text-secondary hover:bg-surface-hover transition-colors"
            data-touch-target="true"
          >
            {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        )}
        <h2 className="hidden sm:block text-lg md:text-xl font-semibold text-primary truncate max-w-[32vw] lg:max-w-none">
          {t('navbar.welcome', { name: user?.display_name || 'Guest' })}
        </h2>
      </div>

      <div className="flex items-center gap-1 md:gap-4 min-w-0">
        {(user?.user_type === 'teacher' || user?.user_type === 'admin') && (
          <a
            href={`${config.BACKEND_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden sm:flex items-center gap-2 px-3 py-2 text-sm font-medium text-brand dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded-lg transition-colors"
            title={t('navbar.apiDocs')}
            data-touch-target="true"
          >
            <BookOpen className="w-4 h-4" />
            <span>{t('navbar.apiDocs')}</span>
          </a>
        )}

        <div className="relative flex-shrink-0">
          <button
            onClick={() => setOpen(v => !v)}
            className="p-2 text-secondary hover:bg-surface-hover dark:hover:bg-gray-700 rounded-full relative transition-colors"
            aria-label="Notifications"
            data-touch-target="true"
          >
            <Bell className="w-5 h-5" />
            {unread > 0 && <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full"></span>}
          </button>
          {open && <NotificationsPanel onClose={() => setOpen(false)} />}
        </div>

        <div className="flex items-center gap-2 md:gap-3 pl-2 md:pl-4 border-l border-border dark:border-white/10 min-w-0">
          <Link to="/settings" className="flex items-center gap-3 hover:opacity-80 transition-opacity flex-shrink-0">
            <div className="w-8 h-8 bg-indigo-100 dark:bg-white/10 rounded-full flex items-center justify-center text-brand dark:text-white">
              <User className="w-5 h-5" />
            </div>
            <div className="hidden md:block">
              <p className="text-sm font-medium text-primary">{user?.display_name || 'Guest'}</p>
              <p className="text-xs text-muted capitalize">{user?.user_type || 'Visitor'}</p>
            </div>
          </Link>
          <div className="ml-1 sm:ml-2 md:ml-4 min-w-0">
            <LanguageSwitcher />
          </div>
        </div>
      </div>
    </header>
  );
}
