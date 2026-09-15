import { Link, useLocation, useNavigate } from 'react-router';
import { LayoutDashboard, BookOpen, Settings, LogOut, Grid, Trophy, Image as ImageIcon, Gamepad2, Users, MessageSquare, Shield } from 'lucide-react';
import { cn } from '../lib/utils';
import { useAuthStore } from '../store/authStore';
import { useTranslation } from 'react-i18next';

interface SidebarProps {
  className?: string;
  isOpen?: boolean;
  onNavigate?: () => void;
}

// Route -> lazy page chunk, warmed on hover so navigation feels instant.
// Kept at module scope so the hover handler stays a one-liner and every
// loader is attached a rejection handler (H43/H64).
const PRELOADABLE_PAGES: Record<string, () => Promise<unknown>> = {
  '/': () => import('../pages/Dashboard'),
  '/communication': () => import('../pages/Communication'),
  '/boards': () => import('../pages/Boards'),
  '/symbols': () => import('../pages/Symbols'),
  '/learning': () => import('../pages/Learning'),
  '/symbol-hunt': () => import('../pages/SymbolHunt'),
  '/achievements': () => import('../pages/Achievements'),
  '/students': () => import('../pages/Students'),
  '/teachers': () => import('../pages/UserManagement'),
  '/admins': () => import('../pages/UserManagement'),
  '/settings': () => import('../pages/Settings'),
};

export function Sidebar({ className, isOpen = true, onNavigate }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useAuthStore(state => state.logout);
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('sidebar');

  const handleLogout = async () => {
    await logout();
    onNavigate?.();
    navigate('/login');
  };

  const links = [
    { href: '/', label: t('links.dashboard'), icon: LayoutDashboard, roles: ['admin', 'teacher', 'student'] },
    { href: '/communication', label: t('links.communication'), icon: MessageSquare, roles: ['admin', 'teacher', 'student'] },
    { href: '/boards', label: t('links.boards'), icon: Grid, roles: ['admin', 'teacher', 'student'] },
    { href: '/symbols', label: t('links.symbols'), icon: ImageIcon, roles: ['admin', 'teacher'] },
    { href: '/learning', label: t('links.learning'), icon: BookOpen, roles: ['admin', 'teacher', 'student'] },
    { href: '/symbol-hunt', label: t('links.symbolHunt'), icon: Gamepad2, roles: ['admin', 'teacher', 'student'] },
    { href: '/achievements', label: t('links.achievements'), icon: Trophy, roles: ['admin', 'teacher', 'student'] },
    { href: '/students', label: t('links.students'), icon: BookOpen, roles: ['admin', 'teacher'] },
    { href: '/teachers', label: t('links.teachers'), icon: Users, roles: ['admin'] },
    { href: '/admins', label: t('links.admins'), icon: Shield, roles: ['admin'] },
    { href: '/settings', label: t('links.settings'), icon: Settings, roles: ['admin', 'teacher', 'student'] },
  ];

  const filteredLinks = links.filter(link =>
    !link.roles || (user && link.roles.includes(user.user_type))
  );

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex h-dvh w-64 -translate-x-full flex-col border-r border-border bg-surface shadow-xl transition-transform duration-300 md:static md:z-auto md:h-auto md:translate-x-0 md:shrink-0 md:shadow-none bg-surface/90 dark:backdrop-blur-xl",
        isOpen && "translate-x-0",
        className
      )}
      aria-label={t('appName')}
    >
      <div className="p-6 border-b border-border/20">
        <h1 className="text-2xl font-bold text-brand dark:drop-shadow-none">{t('appName')}</h1>
      </div>

      <nav className="flex-1 p-4 space-y-2">
        {filteredLinks.map((link) => {
          const Icon = link.icon;
          const isActive = location.pathname === link.href;

          return (
            <Link
              key={link.href}
              to={link.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 group relative overflow-hidden",
                isActive
                  ? "bg-brand/10 text-brand shadow-sm shadow-neon"
                  : "text-muted-foreground hover:bg-surface-hover hover:text-brand"
              )}
              onClick={() => onNavigate?.()}
              onMouseEnter={() => {
                // Attach a rejection handler to the import promise itself: the
                // previous `try/catch` around a bare `import()` could never
                // see an async chunk failure, which surfaced as an
                // unhandledrejection instead of the intended silent skip.
                void PRELOADABLE_PAGES[link.href]?.().catch(() => {});
              }}
            >
              <Icon className="w-5 h-5" />
              <span className="font-medium">{link.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-border/20">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-3 w-full text-left text-muted-foreground hover:bg-surface-hover hover:text-red-600 dark:hover:text-red-400 rounded-lg transition-colors"
          data-touch-target="true"
        >
          <LogOut className="w-5 h-5" />
          <span className="font-medium">{t('signOut')}</span>
        </button>
      </div>
    </aside>
  );
}
