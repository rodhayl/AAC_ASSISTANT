import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const STORAGE_KEY = 'theme-storage';

interface ThemeState {
  darkMode: boolean;
  highContrast: boolean;
  setDarkMode: (enabled: boolean) => void;
  setHighContrast: (enabled: boolean) => void;
}

/**
 * Read the persisted appearance synchronously. Runs at module load so the
 * `dark` / `high-contrast` classes are on <html> before the first paint,
 * even on the login screen where the server settings are not loaded yet.
 * Legacy entries (stored before high contrast existed) only carry darkMode.
 */
function readStoredAppearance(): Pick<ThemeState, 'darkMode' | 'highContrast'> {
  if (typeof window === 'undefined') {
    return { darkMode: false, highContrast: false };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { darkMode: false, highContrast: false };
    const parsed = JSON.parse(raw) as { state?: Partial<ThemeState> };
    return {
      darkMode: parsed.state?.darkMode === true,
      highContrast: parsed.state?.highContrast === true,
    };
  } catch {
    // Corrupted storage must never crash the app or force a wrong theme.
    return { darkMode: false, highContrast: false };
  }
}

/**
 * Browser chrome color that follows the theme: light/white surfaces in light
 * mode, dark surfaces in dark mode, and pure white/black in high contrast.
 */
function themeColor(darkMode: boolean, highContrast: boolean): string {
  if (darkMode) return highContrast ? '#000000' : '#111827';
  return '#ffffff';
}

/** Apply both appearance flags to the document root in one place. */
function applyAppearance(darkMode: boolean, highContrast: boolean) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.toggle('dark', darkMode);
  root.classList.toggle('high-contrast', highContrast);
  let meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', 'theme-color');
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', themeColor(darkMode, highContrast));
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      ...readStoredAppearance(),

      setDarkMode: (enabled) => {
        set({ darkMode: enabled });
        applyAppearance(enabled, get().highContrast);
      },

      setHighContrast: (enabled) => {
        set({ highContrast: enabled });
        applyAppearance(get().darkMode, enabled);
      },
    }),
    { name: STORAGE_KEY }
  )
);

// Apply before React renders so the persisted appearance is active on the very
// first paint. The persist middleware rehydrates from the same key with the
// same values, so this is idempotent and cannot fight the stored state.
applyAppearance(useThemeStore.getState().darkMode, useThemeStore.getState().highContrast);