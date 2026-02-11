import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useLocaleStore } from '../store/localeStore';
import { useThemeStore } from '../store/themeStore';
import { useTTSStore } from '../store/ttsStore';

export function SettingsManager() {
  const { user } = useAuthStore();
  const { setLocale } = useLocaleStore();
  const { setDarkMode } = useThemeStore();
  const { setSelectedVoice } = useTTSStore();

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

      // Apply Locale
      if (user.settings.ui_language) {
        setLocale(user.settings.ui_language);
      }
      
      // Apply TTS Voice
      if (user.settings.tts_voice) {
          setSelectedVoice(user.settings.tts_voice);
      }
    }
  }, [user?.settings, setLocale, setDarkMode, setSelectedVoice]);

  return null;
}
