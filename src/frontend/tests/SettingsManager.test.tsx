import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { SettingsManager } from '../src/components/SettingsManager';
import { useAuthStore } from '../src/store/authStore';
import { useThemeStore } from '../src/store/themeStore';

const mockLocale = { locale: 'es-ES', setLocale: vi.fn().mockResolvedValue(undefined) };
vi.mock('../src/store/localeStore', () => ({
  useLocaleStore: Object.assign(
    (selector?: (state: typeof mockLocale) => unknown) =>
      selector ? selector(mockLocale) : mockLocale,
    { getState: () => mockLocale },
  ),
}));

const mockTTS = {
  setSelectedVoice: vi.fn(),
  setTTSProvider: vi.fn(),
  setLocalVoice: vi.fn(),
};
vi.mock('../src/store/ttsStore', () => ({
  useTTSStore: Object.assign(
    (selector?: (state: typeof mockTTS) => unknown) => (selector ? selector(mockTTS) : mockTTS),
    { getState: () => mockTTS },
  ),
}));

vi.mock('../src/lib/tts', () => ({ warmup: vi.fn() }));

const makeUser = (settings: Record<string, unknown>) => ({
  id: 1,
  username: 'student1',
  display_name: 'Student',
  user_type: 'student' as const,
  settings,
});

describe('SettingsManager appearance application', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark', 'high-contrast');
    // The theme store is a module singleton; reset both flags so tests do not
    // leak state into each other.
    useThemeStore.getState().setDarkMode(false);
    useThemeStore.getState().setHighContrast(false);
    useAuthStore.setState({ user: null, isAuthenticated: false });
  });

  afterEach(() => {
    document.documentElement.classList.remove('dark', 'high-contrast');
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('applies dark and high contrast classes from the persisted settings', () => {
    useAuthStore.setState({
      user: makeUser({ dark_mode: true, high_contrast: true }),
      isAuthenticated: true,
    });

    render(<SettingsManager />);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(true);
    expect(useThemeStore.getState().darkMode).toBe(true);
    expect(useThemeStore.getState().highContrast).toBe(true);
  });

  it('applies only dark mode when high contrast is off', () => {
    useAuthStore.setState({
      user: makeUser({ dark_mode: true, high_contrast: false }),
      isAuthenticated: true,
    });

    render(<SettingsManager />);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(false);
  });

  it('keeps the local appearance when the settings omit legacy fields', () => {
    // Legacy users may lack high_contrast in their settings; the manager must
    // not force light mode on them.
    useThemeStore.getState().setHighContrast(true);
    useAuthStore.setState({
      user: makeUser({ dark_mode: false }),
      isAuthenticated: true,
    });

    render(<SettingsManager />);

    expect(document.documentElement.classList.contains('high-contrast')).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('does nothing while no user is logged in (login screen keeps local theme)', () => {
    useThemeStore.getState().setDarkMode(true);

    render(<SettingsManager />);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('high-contrast')).toBe(false);
  });
});