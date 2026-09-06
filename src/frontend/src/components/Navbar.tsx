import { Bell, User, BookOpen, Menu, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useAuthStore } from '../store/authStore';
import { useNotificationsStore } from '../store/notificationsStore';
import { NotificationsPanel } from './NotificationsPanel';
import { config } from '../config';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';
import { isStaffUser } from '../lib/roles';
import { isAbortError } from '../lib/httpErrors';

interface NavbarProps {
  onMenuToggle?: () => void;
  isSidebarOpen?: boolean;
}

export function Navbar({ onMenuToggle, isSidebarOpen = false }: NavbarProps) {
  const user = useAuthStore(state => state.user);
  const token = useAuthStore(state => state.token);
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
    // Respect the user's notification preference: a disabled setting means the
    // bell must not open a live push stream (it is persisted but was previously
    // never consumed by any reader).
    if (!user?.id || !token || user.settings?.notifications_enabled === false) return;

    // Authenticate the stream with a bearer header. EventSource cannot set
    // headers, so use fetch and consume the SSE body instead of putting the
    // JWT in a query string where access logs and browser history can retain it.
    const controller = new AbortController();
    const maxRetryDelay = 30000;
    let retryDelay = 1000;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    // A 401 means the token is invalid or expired; the auth flow will refresh
    // or log out, and reconnecting would only hammer the server forever.
    let unauthorized = false;

    const consumeStream = async () => {
      try {
        const response = await fetch(`${config.API_BASE_URL}/notifications/stream`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          if (response.status === 401) unauthorized = true;
          throw new Error(`HTTP ${response.status}`);
        }

        // A successful connection resets the backoff so a brief hiccup does not
        // accumulate into a long silence.
        retryDelay = 1000;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split(/\r?\n\r?\n/);
          buffer = events.pop() || '';
          for (const event of events) {
            const dataLine = event
              .split(/\r?\n/)
              .find((line) => line.startsWith('data:'));
            if (!dataLine) continue;
            try {
              const data = JSON.parse(dataLine.slice(5).trim() || '{}');
              if (data?.title && data?.message) {
                useNotificationsStore.getState().add({
                  title: data.title,
                  message: data.message,
                  type: data.type || 'info',
                });
              }
            } catch {
              // Ignore malformed individual events; one bad notification
              // must not terminate the stream.
            }
          }
        }
        } catch (error) {
        if (isAbortError(error)) return;
        // Notification delivery is optional and must not disrupt the AAC UI.
      }

      // The stream ended or dropped; reconnect with exponential backoff so a
      // transient outage does not permanently silence the notification bell.
      // An invalid session must not keep retrying, though.
      if (!controller.signal.aborted && !unauthorized) {
        const delay = retryDelay;
        retryDelay = Math.min(retryDelay * 2, maxRetryDelay);
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          if (!controller.signal.aborted) void consumeStream();
        }, delay);
      }
    };

    void consumeStream();
    return () => {
      controller.abort();
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
    };
  }, [token, user?.id, user?.settings?.notifications_enabled])

  return (
    <header className="h-16 bg-surface/90 dark:bg-transparent backdrop-blur-sm border-b border-border/20 flex items-center justify-between gap-2 px-4 md:px-6 transition-all duration-200 z-10 sticky top-0">
      <div className="flex items-center gap-3 min-w-0">
        {onMenuToggle && (
          <button
            type="button"
            onClick={onMenuToggle}
            aria-label={t('navbar.toggleMenu')}
            aria-expanded={isSidebarOpen}
            className="md:hidden rounded-lg p-2 text-muted-foreground hover:bg-surface-hover transition-colors"
            data-touch-target="true"
          >
            {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        )}
        <h2 className="hidden sm:block text-lg md:text-xl font-semibold text-foreground truncate max-w-[32vw] lg:max-w-none">
          {t('navbar.welcome', { name: user?.display_name || t('navbar.guest') })}
        </h2>
      </div>

      <div className="flex items-center gap-1 md:gap-4 min-w-0">
        {isStaffUser(user) && (
          <a
            href={`${config.BACKEND_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden sm:flex items-center gap-2 px-3 py-2 text-sm font-medium text-brand hover:bg-brand/20 rounded-lg transition-colors"
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
            className="p-2 text-muted-foreground hover:bg-surface-hover rounded-full relative transition-colors"
            aria-label={t('notifications.title')}
            data-touch-target="true"
          >
            <Bell className="w-5 h-5" />
            {unread > 0 && <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full"></span>}
          </button>
          {open && <NotificationsPanel onClose={() => setOpen(false)} />}
        </div>

        <div className="flex items-center gap-2 md:gap-3 pl-2 md:pl-4 border-l border-border/20 min-w-0">
          <Link to="/settings" className="flex items-center gap-3 hover:opacity-80 transition-opacity flex-shrink-0">
            <div className="w-8 h-8 bg-brand/10 rounded-full flex items-center justify-center text-brand">
              <User className="w-5 h-5" />
            </div>
            <div className="hidden md:block">
              <p className="text-sm font-medium text-foreground">{user?.display_name || t('navbar.guest')}</p>
              <p className="text-xs text-muted-foreground capitalize">{user?.user_type ? t(`navbar.roles.${user.user_type}`) : t('navbar.visitor')}</p>
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
