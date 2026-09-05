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

  useEffect(() => {
    if (user?.settings) {
      // Apply appearance flags (the store owns the `dark` / `high-contrast`
      // document classes). Absent legacy fields fall back to the current
      // local appearance instead of forcing light mode.
      if (user.settings.dark_mode !== undefined) {
        setDarkMode(user.settings.dark_mode);
      }
      if (user.settings.high_contrast !== undefined) {
        setHighContrast(user.settings.high_contrast);
      }

      // Apply Locale (normalize legacy short codes so the switcher select
      // matches regardless of how the value was persisted)
      if (user.settings.ui_language) {
        setLocale(normalizeUILanguage(user.settings.ui_language));
      }
      
      // Apply TTS Voice
      if (user.settings.tts_voice) {
          setSelectedVoice(user.settings.tts_voice);
      }
      setTTSProvider(user.settings.tts_provider === 'browser' ? 'browser' : 'kokoro');
      if (user.settings.tts_local_voice) {
        setLocalVoice(user.settings.tts_local_voice);
      }
      if (user.settings.tts_local_speed !== undefined) {
        setLocalSpeed(user.settings.tts_local_speed);
      }
      // Warm every lazy model (browser voice list, capability check, and the
      // backend Kokoro + faster-whisper models) in one batched background
      // request so the first spoken message and the first microphone answer
      // in a conversation are not delayed.
      warmup();
    }
  }, [user?.settings, setLocale, setDarkMode, setHighContrast, setSelectedVoice, setTTSProvider, setLocalVoice, setLocalSpeed]);

  return null;
}
