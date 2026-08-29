import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const STORAGE_KEY = 'theme-storage';

describe('themeStore', () => {
  function themeColorMeta() {
    return document.querySelector('meta[name="theme-color"]');
  }

  beforeEach(() => {
    localStorage.removeItem(STORAGE_KEY);
    document.documentElement.classList.remove('dark', 'high-contrast');
    document.querySelector('meta[name="theme-color"]')?.remove();
    vi.resetModules();
  });

  afterEach(() => {
    document.documentElement.classList.remove('dark', 'high-contrast');
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

  it('toggles high contrast independently and persists both flags', async () => {
    const { useThemeStore } = await import('../src/store/themeStore');
    const setHighContrast = useThemeStore.getState().setHighContrast;

    expect(document.documentElement.classList.contains('high-contrast')).toBe(false);

    setHighContrast(true);
    expect(useThemeStore.getState().highContrast).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(true);

    // Dark stays independent of high contrast.
    useThemeStore.getState().setDarkMode(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(true);

    // The persisted snapshot carries both flags for rehydration.
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
    expect(stored.state.darkMode).toBe(true);
    expect(stored.state.highContrast).toBe(true);

    setHighContrast(false);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(false);
    expect(useThemeStore.getState().highContrast).toBe(false);
  });

  it('re-applies the persisted theme after rehydration', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: { darkMode: true } }));

    const { useThemeStore } = await import('../src/store/themeStore');

    await vi.waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true);
    });
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('applies the stored theme on module load (before first paint)', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: { darkMode: true, highContrast: true } }));

    await import('../src/store/themeStore');

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(true);
  });

  it('applies the theme from a legacy entry that only has darkMode', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: { darkMode: true } }));

    const { useThemeStore } = await import('../src/store/themeStore');

    expect(useThemeStore.getState().darkMode).toBe(true);
    expect(useThemeStore.getState().highContrast).toBe(false);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(false);
  });

  it('ignores corrupted theme storage on module load', async () => {
    localStorage.setItem(STORAGE_KEY, 'not-json{');

    const { useThemeStore } = await import('../src/store/themeStore');

    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(false);
    expect(useThemeStore.getState().darkMode).toBe(false);
  });

  it('syncs the theme-color meta with dark mode and high contrast', async () => {
    const { useThemeStore } = await import('../src/store/themeStore');

    // Light default.
    expect(themeColorMeta()?.getAttribute('content')).toBe('#ffffff');

    useThemeStore.getState().setDarkMode(true);
    expect(themeColorMeta()?.getAttribute('content')).toBe('#111827');

    useThemeStore.getState().setHighContrast(true);
    expect(themeColorMeta()?.getAttribute('content')).toBe('#000000');

    useThemeStore.getState().setDarkMode(false);
    expect(themeColorMeta()?.getAttribute('content')).toBe('#ffffff');
  });

  it('applies the persisted theme-color before first paint on module load', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: { darkMode: true } }));

    await import('../src/store/themeStore');

    expect(themeColorMeta()?.getAttribute('content')).toBe('#111827');
  });
});