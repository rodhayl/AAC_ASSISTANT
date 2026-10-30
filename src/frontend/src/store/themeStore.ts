import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ThemeState {
  darkMode: boolean;
  setDarkMode: (enabled: boolean) => void;
  toggleDarkMode: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      darkMode: false,
      
      setDarkMode: (enabled: boolean) => {
        set({ darkMode: enabled });
        applyTheme(enabled);
      },
      
      toggleDarkMode: () => {
        const newValue = !get().darkMode;
        set({ darkMode: newValue });
        applyTheme(newValue);
      },
    }),
    {
      name: 'theme-storage',
      onRehydrateStorage: () => (state) => {
        // Apply theme after rehydration from localStorage
        if (state) {
          applyTheme(state.darkMode);
        }
      },
    }
  )
);

function applyTheme(darkMode: boolean) {
  if (typeof document !== 'undefined') {
    const root = document.documentElement;
    if (darkMode) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }
}

// Initialize theme on module load
if (typeof window !== 'undefined') {
  const stored = localStorage.getItem('theme-storage');
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      if (parsed?.state?.darkMode) {
        document.documentElement.classList.add('dark');
      }
    } catch { /* ignore parse errors */ }
  }
}
