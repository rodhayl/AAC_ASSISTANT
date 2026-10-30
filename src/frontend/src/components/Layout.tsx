import { Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Sidebar } from './Sidebar';
import { Navbar } from './Navbar';
import { OfflineConflictsPanel } from './OfflineConflictsPanel';
import { useTranslation } from 'react-i18next';

export function Layout() {
  const location = useLocation();
  const [isOffline, setIsOffline] = useState<boolean>(typeof navigator !== 'undefined' ? !navigator.onLine : false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { t } = useTranslation('layout');

  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  useEffect(() => {
    setIsSidebarOpen(false);
  }, [location.pathname]);

  return (
    <>
      <a href="#main-content" className="skip-to-main">
        {t('skip')}
      </a>
      <div className="flex min-h-dvh bg-transparent transition-colors duration-200">
        <Sidebar
          className="z-40"
          isOpen={isSidebarOpen}
          onNavigate={() => setIsSidebarOpen(false)}
        />
        {isSidebarOpen && (
          <button
            type="button"
            aria-label={t('closeSidebar', { defaultValue: 'Close sidebar' })}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 z-30 bg-black/40 backdrop-blur-[1px] md:hidden"
          />
        )}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
          <Navbar onMenuToggle={() => setIsSidebarOpen(v => !v)} isSidebarOpen={isSidebarOpen} />
          {isOffline && (
            <div className="px-4 md:px-6 py-2 bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 border-b border-amber-200 dark:border-amber-800 text-sm" role="status" aria-live="polite">
              {t('offline')}
            </div>
          )}
          <main id="main-content" className="flex-1 overflow-auto bg-transparent relative" role="main" aria-label={t('main')}>
            <Outlet />
          </main>
        </div>
        <OfflineConflictsPanel />
      </div>
    </>
  );
}
