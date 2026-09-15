import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useLocaleStore } from '../store/localeStore';
import { useThemeStore } from '../store/themeStore';
import { useTTSStore } from '../store/ttsStore';
import { normalizeUILanguage } from '../lib/utils';
import { warmup } from '../lib/tts';

export function SettingsManager() {
  const user = useAuthStore(state => state.user);
  const setLocale = useLocaleStore((state) => state.setLocale);
  const setDarkMode = useThemeStore((state) => state.setDarkMode);
  const setHighContrast = useThemeStore((state) => state.setHighContrast);
  const setSelectedVoice = useTTSStore((state) => state.setSelectedVoice);
  const setTTSProvider = useTTSStore((state) => state.setTTSProvider);
  const setLocalVoice = useTTSStore((state) => state.setLocalVoice);
  const setLocalSpeed = useTTSStore((state) => state.setLocalSpeed);

  // Depend on the consumed values, not the whole `settings` object: the auth
  // store replaces that object on every profile refresh, which re-applied the
  // locale and re-fired the backend model warmup each time (H41).
  const settings = user?.settings;
  const hasSettings = settings !== undefined;
  const darkModeSetting = settings?.dark_mode;
  const highContrastSetting = settings?.high_contrast;
  const uiLanguageSetting = settings?.ui_language;
  const ttsVoiceSetting = settings?.tts_voice;
  const ttsProviderSetting = settings?.tts_provider;
  const ttsLocalVoiceSetting = settings?.tts_local_voice;
  const ttsLocalSpeedSetting = settings?.tts_local_speed;

  useEffect(() => {
    if (hasSettings) {
      // Apply appearance flags (the store owns the `dark` / `high-contrast`
      // document classes). Absent legacy fields fall back to the current
      // local appearance instead of forcing light mode.
      if (darkModeSetting !== undefined) {
        setDarkMode(darkModeSetting);
      }
      if (highContrastSetting !== undefined) {
        setHighContrast(highContrastSetting);
      }

      // Apply Locale (normalize legacy short codes so the switcher select
      // matches regardless of how the value was persisted)
      if (uiLanguageSetting) {
        setLocale(normalizeUILanguage(uiLanguageSetting));
      }

      // Apply TTS Voice
      if (ttsVoiceSetting) {
        setSelectedVoice(ttsVoiceSetting);
      }
      setTTSProvider(ttsProviderSetting === 'browser' ? 'browser' : 'kokoro');
      if (ttsLocalVoiceSetting) {
        setLocalVoice(ttsLocalVoiceSetting);
      }
      if (ttsLocalSpeedSetting !== undefined) {
        setLocalSpeed(ttsLocalSpeedSetting);
      }
      // Warm every lazy model (browser voice list, capability check, and the
      // backend Kokoro + faster-whisper models) in one batched background
      // request so the first spoken message and the first microphone answer
      // in a conversation are not delayed.
      warmup();
    }
  }, [
    hasSettings,
    darkModeSetting,
    highContrastSetting,
    uiLanguageSetting,
    ttsVoiceSetting,
    ttsProviderSetting,
    ttsLocalVoiceSetting,
    ttsLocalSpeedSetting,
    setLocale,
    setDarkMode,
    setHighContrast,
    setSelectedVoice,
    setTTSProvider,
    setLocalVoice,
    setLocalSpeed,
  ]);

  return null;
}
