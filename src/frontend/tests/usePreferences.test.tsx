import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { usePreferences } from '../src/pages/Settings/usePreferences';
import { useAuthStore } from '../src/store/authStore';

const { get, put } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}));

vi.mock('../src/lib/api', () => ({
  default: { get, put },
  extractError: (error: { message?: string } | undefined, fallback: string) =>
    error?.message || fallback,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => {
      // Mirrors the production locale: settings.errors.saveFailed resolves to
      // real text (it used to render the raw key in the settings namespace).
      const table: Record<string, string> = {
        'errors.saveFailed': 'Failed to save preferences',
        'preferences.saved': 'Saved',
      };
      return table[key] ?? defaultValue ?? key;
    },
    i18n: { language: 'en-US' },
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
}));

describe('usePreferences', () => {
  it('does not overwrite a user edit when the initial preferences GET resolves late', async () => {
    // A deferred GET simulates a slow network: the server value arrives only
    // after the user has already changed a preference.
    let resolveGet: (value: { data: Record<string, unknown> }) => void = () => {};
    get.mockImplementation(
      () =>
        new Promise<{ data: Record<string, unknown> }>((resolve) => {
          resolveGet = resolve;
        }),
    );

    const { result } = renderHook(() => usePreferences());

    // The user disables voice mode before the GET response arrives.
    act(() => {
      result.current.setPreferences((prev) => ({
        ...prev,
        voice_mode_enabled: false,
      }));
    });

    // The slow GET now returns the server default (true). It must not clobber
    // the user's edit.
    await act(async () => {
      resolveGet({
        data: {
          tts_provider: 'kokoro',
          tts_voice: 'default',
          tts_local_voice: 'default',
          ui_language: 'es-ES',
          notifications_enabled: true,
          voice_mode_enabled: true,
          dark_mode: false,
          dwell_time: 0,
          ignore_repeats: 0,
          high_contrast: false,
        },
      });
    });

    expect(result.current.preferences.voice_mode_enabled).toBe(false);
  });

  it('applies the fetched preferences when the user has not edited', async () => {
    get.mockResolvedValue({
      data: {
        tts_provider: 'kokoro',
        tts_voice: 'es-voice',
        tts_local_voice: 'ef_dora',
        ui_language: 'en-US',
        notifications_enabled: false,
        voice_mode_enabled: false,
        dark_mode: true,
        dwell_time: 300,
        ignore_repeats: 100,
        high_contrast: true,
      },
    });

    const { result } = renderHook(() => usePreferences());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.preferences.voice_mode_enabled).toBe(false);
    expect(result.current.preferences.ui_language).toBe('en-US');
    expect(result.current.preferences.dark_mode).toBe(true);
  });

  it('surfaces a translated error when saving preferences fails', async () => {
    useAuthStore.setState({
      user: {
        id: 1,
        username: 'student1',
        display_name: 'Student',
        user_type: 'student',
        settings: {},
      },
    });
    get.mockResolvedValue({ data: {} });
    put.mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => usePreferences());

    await act(async () => {
      await result.current.handleSavePreferences();
    });

    // The error must be the translated message, never the raw key.
    expect(result.current.prefsSaveError).toBe('Failed to save preferences');
  });

  it('normalizes a legacy short ui_language so it matches the select options', async () => {
    // The navbar LanguageSwitcher used to persist "en"; the appearance select
    // only offers es-ES / en-US. A stored short code must be normalized so the
    // select shows the correct language instead of silently falling back.
    get.mockResolvedValue({
      data: {
        tts_provider: 'kokoro',
        tts_voice: 'default',
        tts_local_voice: 'default',
        ui_language: 'en',
        notifications_enabled: true,
        voice_mode_enabled: true,
        dark_mode: false,
        dwell_time: 0,
        ignore_repeats: 0,
        high_contrast: false,
      },
    });

    const { result } = renderHook(() => usePreferences());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.preferences.ui_language).toBe('en-US');
  });
});
