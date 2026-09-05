import { Toaster as SonnerToaster } from 'sonner'

import { useThemeStore } from '../../store/themeStore'

/**
 * App-wide sonner Toaster mounted once in App's RootLayout.
 *
 * The `.aac-toast` palette in index.css reuses the exact classes the old
 * hand-rolled ToastContainer was audited with (light/dark/high-contrast).
 */
export function AppToaster() {
  const darkMode = useThemeStore((state) => state.darkMode);

  return (
    <SonnerToaster
      theme={darkMode ? 'dark' : 'light'}
      position="bottom-right"
      closeButton
      // sonner's default container label is "Notifications alt+T", which
      // collides with the Navbar bell's aria-label="Notifications" and made
      // every getByLabel(/notifications/i) ambiguous for users and tests.
      containerAriaLabel="Alerts"
      toastOptions={{ classNames: { toast: 'aac-toast' } }}
    />
  );
}
