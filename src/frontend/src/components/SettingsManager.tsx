import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useLocaleStore } from '../store/localeStore';
import { useThemeStore } from '../store/themeStore';
import { useTTSStore } from '../store/ttsStore';
import { normalizeUILanguage } from '../lib/utils';

export function SettingsManager() {
  const user = useAuthStore(state => state.user);
  const setLocale = useLocaleStore((state) => state.setLocale);
  const setDarkMode = useThemeStore((state) => state.setDarkMode);
  const setSelectedVoice = useTTSStore((state) => state.setSelectedVoice);
  const setTTSProvider = useTTSStore((state) => state.setTTSProvider);
  const setLocalVoice = useTTSStore((state) => state.setLocalVoice);

  useEffect(() => {
    if (user?.settings) {
      // Apply High Contrast
      if (user.settings.high_contrast) {
        document.documentElement.classList.add('high-contrast');
      } else {
        document.documentElement.classList.remove('high-contrast');
      }

      // Apply Dark Mode
      if (user.settings.dark_mode !== undefined) {
         setDarkMode(user.settings.dark_mode);
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
    }
  }, [user?.settings, setLocale, setDarkMode, setSelectedVoice, setTTSProvider, setLocalVoice]);

  return null;
}
