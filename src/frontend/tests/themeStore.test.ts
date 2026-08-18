import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const STORAGE_KEY = 'theme-storage';

describe('themeStore', () => {
  beforeEach(() => {
    localStorage.removeItem(STORAGE_KEY);
    document.documentElement.classList.remove('dark');
    vi.resetModules();
  });

  afterEach(() => {
    document.documentElement.classList.remove('dark');
    localStorage.removeItem(STORAGE_KEY);
  });

  it('sets dark mode explicitly and applies/removes the theme class', async () => {
    const { useThemeStore } = await import('../src/store/themeStore');

    expect(useThemeStore.getState().darkMode).toBe(false);
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    useThemeStore.getState().setDarkMode(true);
    expect(useThemeStore.getState().darkMode).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    useThemeStore.getState().setDarkMode(false);
    expect(useThemeStore.getState().darkMode).toBe(false);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('re-applies the persisted theme after rehydration', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: { darkMode: true } }));

    const { useThemeStore } = await import('../src/store/themeStore');

    await vi.waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true);
    });
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('applies the stored theme on module load', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: { darkMode: true } }));

    await import('../src/store/themeStore');

    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('ignores corrupted theme storage on module load', async () => {
    localStorage.setItem(STORAGE_KEY, 'not-json{');

    await expect(import('../src/store/themeStore')).resolves.toBeDefined();

    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});
