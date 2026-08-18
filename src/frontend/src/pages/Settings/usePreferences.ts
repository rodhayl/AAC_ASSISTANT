import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuthStore } from '../../store/authStore';
import { useLocaleStore } from '../../store/localeStore';
import { useThemeStore } from '../../store/themeStore';
import { useTTSStore } from '../../store/ttsStore';
import api from '../../lib/api';
import { useToastStore } from '../../store/toastStore';
import { useTranslation } from 'react-i18next';
import type { Preferences } from './types';

const defaultPreferences = (user: ReturnType<typeof useAuthStore.getState>['user']): Preferences => ({
  tts_provider: user?.settings?.tts_provider === 'browser' ? 'browser' : 'kokoro',
  tts_voice: user?.settings?.tts_voice || 'default',
  tts_local_voice: user?.settings?.tts_local_voice || 'default',
  ui_language: user?.settings?.ui_language || 'es-ES',
  notifications_enabled: user?.settings?.notifications_enabled ?? true,
  voice_mode_enabled: user?.settings?.voice_mode_enabled ?? true,
  dark_mode: user?.settings?.dark_mode ?? false,
  dwell_time: user?.settings?.dwell_time ?? 0,
  ignore_repeats: user?.settings?.ignore_repeats ?? 0,
  high_contrast: user?.settings?.high_contrast ?? false,
});

export function usePreferences() {
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('settings');
  const addToast = useToastStore((state) => state.addToast);
  const [preferences, setPreferencesState] = useState<Preferences>(() => defaultPreferences(user));
  // Once the user edits a preference, the async initial hydration must not
  // overwrite their change (a slow GET could otherwise revert it).
  const userEditedRef = useRef(false);
  const setPreferences = useCallback(
    (updater: Parameters<typeof setPreferencesState>[0]) => {
      userEditedRef.current = true;
      setPreferencesState(updater);
    },
    [],
  );
  const [prefsLoading, setPrefsLoading] = useState(false);
  const [prefsSaveSuccess, setPrefsSaveSuccess] = useState(false);
  const [prefsSaveError, setPrefsSaveError] = useState<string | null>(null);
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const res = await api.get('/auth/preferences');
        // Do not clobber edits made before the initial hydration resolved.
        if (userEditedRef.current) return;
        const voice = res.data.tts_voice || 'default';
        const darkMode = res.data.dark_mode ?? false;
        const language = res.data.ui_language || 'es-ES';

        setPreferencesState({
          tts_provider: res.data.tts_provider === 'browser' ? 'browser' : 'kokoro',
          tts_voice: voice,
          tts_local_voice: res.data.tts_local_voice || 'default',
          ui_language: language,
          notifications_enabled: res.data.notifications_enabled ?? true,
          voice_mode_enabled: res.data.voice_mode_enabled ?? true,
          dark_mode: darkMode,
          dwell_time: res.data.dwell_time ?? 0,
          ignore_repeats: res.data.ignore_repeats ?? 0,
          high_contrast: res.data.high_contrast ?? false,
        });
        useTTSStore.getState().setSelectedVoice(voice);
        useTTSStore.getState().setTTSProvider(res.data.tts_provider === 'browser' ? 'browser' : 'kokoro');
        useTTSStore.getState().setLocalVoice(res.data.tts_local_voice || 'default');
        useThemeStore.getState().setDarkMode(darkMode);
        useLocaleStore.getState().setLocale(language);
      } catch (err) {
        console.error('Failed to load preferences:', err);
      }
    };
    loadPreferences();
  }, []);

  useEffect(() => {
    const speechSynthesis = window.speechSynthesis;
    if (!speechSynthesis) return undefined;

    const loadVoices = () => {
      setAvailableVoices(speechSynthesis.getVoices());
    };

    loadVoices();
    if (speechSynthesis.addEventListener) {
      speechSynthesis.addEventListener('voiceschanged', loadVoices);
      return () => speechSynthesis.removeEventListener('voiceschanged', loadVoices);
    }
    const previousHandler = speechSynthesis.onvoiceschanged;
    speechSynthesis.onvoiceschanged = loadVoices;
    return () => {
      if (speechSynthesis.onvoiceschanged === loadVoices) {
        speechSynthesis.onvoiceschanged = previousHandler;
      }
    };
  }, []);

  const filteredVoices = useMemo(
    () =>
      availableVoices.filter((voice) => {
        if (preferences.ui_language.startsWith('es')) {
          return voice.lang.startsWith('es');
        }
        return voice.lang.startsWith('en');
      }),
    [availableVoices, preferences.ui_language],
  );

  const handleSavePreferences = async () => {
    setPrefsLoading(true);
    setPrefsSaveSuccess(false);
    setPrefsSaveError(null);
    try {
      if (user) {
        const res = await api.put('/auth/preferences', preferences);
        const { setDarkMode } = useThemeStore.getState();
        const { setLocale } = useLocaleStore.getState();
        const { setSelectedVoice } = useTTSStore.getState();
        const { setTTSProvider, setLocalVoice } = useTTSStore.getState();

        setDarkMode(preferences.dark_mode);
        setLocale(preferences.ui_language);
        setSelectedVoice(preferences.tts_voice);
        setTTSProvider(preferences.tts_provider);
        setLocalVoice(preferences.tts_local_voice);

        useAuthStore.setState((state) => {
          if (!state.user) return state;
          return {
            user: {
              ...state.user,
              settings: {
                ...(state.user.settings || {}),
                ...res.data,
              },
            },
          };
        });

        setPrefsSaveSuccess(true);
        addToast(t('preferences.saved'), 'success');
      }
    } catch (err: unknown) {
      console.error('Failed to save preferences:', err);
      setPrefsSaveError(t('errors.saveFailed'));
      addToast(t('errors.saveFailed'), 'error');
    } finally {
      setPrefsLoading(false);
    }
  };

  return {
    preferences,
    setPreferences,
    filteredVoices,
    prefsLoading,
    prefsSaveSuccess,
    prefsSaveError,
    handleSavePreferences,
  };
}
