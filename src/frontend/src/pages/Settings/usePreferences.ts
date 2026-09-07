import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuthStore } from '../../store/authStore';
import { useLocaleStore } from '../../store/localeStore';
import { useThemeStore } from '../../store/themeStore';
import { useTTSStore } from '../../store/ttsStore';
import api from '../../lib/api';
import { normalizePreferencesResponse, normalizeUILanguage } from '../../lib/utils';
import { useToastStore } from '../../store/toastStore';
import { useTranslation } from 'react-i18next';
import type { Preferences } from './types';
import type { UserPreferences, UserPreferencesResponse } from '../../types';

const defaultPreferences = (user: ReturnType<typeof useAuthStore.getState>['user']): Preferences => ({
  tts_provider: user?.settings?.tts_provider === 'browser' ? 'browser' : 'kokoro',
  tts_voice: user?.settings?.tts_voice || 'default',
  tts_local_voice: user?.settings?.tts_local_voice || 'default',
  tts_local_speed: user?.settings?.tts_local_speed ?? 1.0,
  ui_language: normalizeUILanguage(user?.settings?.ui_language),
  notifications_enabled: user?.settings?.notifications_enabled ?? true,
  voice_mode_enabled: user?.settings?.voice_mode_enabled ?? true,
  dark_mode: user?.settings?.dark_mode ?? false,
  dwell_time: user?.settings?.dwell_time ?? 0,
  ignore_repeats: user?.settings?.ignore_repeats ?? 0,
  high_contrast: user?.settings?.high_contrast ?? false,
  hover_speak_enabled: user?.settings?.hover_speak_enabled ?? false,
  hover_speak_delay_ms: user?.settings?.hover_speak_delay_ms ?? 1000,
  default_learning_mode: user?.settings?.default_learning_mode || 'practice',
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

  const userId = user?.id;
  const preferencesRequestRef = useRef(0);
  const activeUserIdRef = useRef<number | undefined>(userId);

  useEffect(() => {
    const requestId = ++preferencesRequestRef.current;
    activeUserIdRef.current = userId;
    let active = true;
    userEditedRef.current = false;
    const activeUser = useAuthStore.getState().user;
    setPreferencesState(defaultPreferences(activeUser));

    const loadPreferences = async () => {
      try {
        const res = await api.get<UserPreferencesResponse>('/auth/preferences');
        // Do not clobber edits made before the initial hydration resolved, or
        // apply a response belonging to a previous authenticated user.
        if (
          !active ||
          requestId !== preferencesRequestRef.current ||
          activeUserIdRef.current !== userId ||
          userEditedRef.current
        ) return;
        // The same wire-to-store mapping the PUT path uses
        // (normalizePreferencesResponse): both hydration and updateAuthSettings
        // must derive identical state from an identical response.
        const normalized = normalizePreferencesResponse(res.data);
        setPreferencesState(normalized);
        useTTSStore.getState().setSelectedVoice(normalized.tts_voice);
        useTTSStore.getState().setTTSProvider(normalized.tts_provider);
        useTTSStore.getState().setLocalVoice(normalized.tts_local_voice);
        useTTSStore.getState().setLocalSpeed(normalized.tts_local_speed);
        useThemeStore.getState().setDarkMode(normalized.dark_mode);
        useThemeStore.getState().setHighContrast(normalized.high_contrast);
        await useLocaleStore.getState().setLocale(normalized.ui_language);
      } catch (err) {
        if (active) console.error('Failed to load preferences:', err);
      }
    };
    void loadPreferences();
    return () => {
      active = false;
      preferencesRequestRef.current += 1;
    };
  }, [userId]);

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

  const updateAuthSettings = useCallback((data: UserPreferencesResponse) => {
    useAuthStore.setState((state) => {
      if (!state.user) return state;
      // The wire response may carry persisted NULLs (ui_language/tts_language)
      // and a free-form tts_provider string; normalize each field into the
      // typed UserPreferences contract the auth store exposes so no component
      // ever reads null where the type promises a string.
      // Shared wire-to-store mapping (also used by the GET hydration path)
      // so the PUT response cannot drift from the initial fetch.
      const settings: UserPreferences = normalizePreferencesResponse(data);
      return {
        user: {
          ...state.user,
          settings,
        },
      };
    });
  }, []);

  const notifyLearningModeChange = useCallback((defaultModeKey: string) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('aac:learning-modes-changed', {
        detail: { defaultModeKey },
      }));
    }
  }, []);

  const saveDefaultLearningMode = useCallback(async (defaultModeKey: string) => {
    if (!user) return;
    const requestId = ++preferencesRequestRef.current;
    const savedUserId = user.id;
    const previousModeKey = preferences.default_learning_mode || 'practice';
    const isCurrentRequest = () =>
      requestId === preferencesRequestRef.current && activeUserIdRef.current === savedUserId;
    setPreferences((prev) => ({ ...prev, default_learning_mode: defaultModeKey }));
    setPrefsLoading(true);
    setPrefsSaveSuccess(false);
    setPrefsSaveError(null);
    try {
      const res = await api.put<UserPreferencesResponse>('/auth/preferences', {
        default_learning_mode: defaultModeKey,
      });
      if (!isCurrentRequest()) return;
      const savedModeKey = res.data.default_learning_mode || defaultModeKey;
      setPreferencesState((prev) => ({ ...prev, default_learning_mode: savedModeKey }));
      updateAuthSettings(res.data);
      notifyLearningModeChange(savedModeKey);
      setPrefsSaveSuccess(true);
      addToast(t('learningModes.defaultModeSaved'), 'success');
    } catch (err: unknown) {
      if (!isCurrentRequest()) return;
      setPreferencesState((prev) => ({ ...prev, default_learning_mode: previousModeKey }));
      setPrefsSaveError(t('errors.saveFailed'));
      addToast(t('errors.saveFailed'), 'error');
      throw err;
    } finally {
      if (isCurrentRequest()) {
        setPrefsLoading(false);
      }
    }
  }, [addToast, notifyLearningModeChange, preferences.default_learning_mode, setPreferences, t, updateAuthSettings, user]);

  const handleSavePreferences = async () => {
    const savedUserId = user?.id;
    const requestId = ++preferencesRequestRef.current;
    const isCurrentRequest = () =>
      requestId === preferencesRequestRef.current &&
      activeUserIdRef.current === savedUserId;
    setPrefsLoading(true);
    setPrefsSaveSuccess(false);
    setPrefsSaveError(null);
    try {
      if (user) {
        const res = await api.put<UserPreferencesResponse>('/auth/preferences', preferences);
        if (!isCurrentRequest()) return;
        const { setDarkMode, setHighContrast } = useThemeStore.getState();
        const { setLocale } = useLocaleStore.getState();
        const { setSelectedVoice } = useTTSStore.getState();
        const { setTTSProvider, setLocalVoice, setLocalSpeed } = useTTSStore.getState();

        setDarkMode(preferences.dark_mode);
        setHighContrast(preferences.high_contrast);
        await setLocale(preferences.ui_language);
        if (!isCurrentRequest()) return;
        setSelectedVoice(preferences.tts_voice);
        setTTSProvider(preferences.tts_provider);
        setLocalVoice(preferences.tts_local_voice);
        setLocalSpeed(preferences.tts_local_speed);

        updateAuthSettings(res.data);
        notifyLearningModeChange(preferences.default_learning_mode || 'practice');
        setPrefsSaveSuccess(true);
        addToast(t('preferences.saved'), 'success');
      }
    } catch (err: unknown) {
      if (isCurrentRequest()) {
        console.error('Failed to save preferences:', err);
        setPrefsSaveError(t('errors.saveFailed'));
        addToast(t('errors.saveFailed'), 'error');
      }
    } finally {
      if (isCurrentRequest()) {
        setPrefsLoading(false);
      }
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
    saveDefaultLearningMode,
  };
}
