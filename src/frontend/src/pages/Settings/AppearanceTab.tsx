import type { Dispatch, SetStateAction } from 'react';
import { AlertCircle, Bell, Check, Clock, Eye, Globe, Moon, MousePointer, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Toggle } from '../../components/ui/Toggle';
import type { Preferences } from './types';

interface AppearanceTabProps {
  preferences: Preferences;
  setPreferences: Dispatch<SetStateAction<Preferences>>;
  prefsLoading: boolean;
  prefsSaveSuccess: boolean;
  prefsSaveError: string | null;
  onSave: () => Promise<void>;
}

export function AppearanceTab({
  preferences,
  setPreferences,
  prefsLoading,
  prefsSaveSuccess,
  prefsSaveError,
  onSave,
}: AppearanceTabProps) {
  const { t } = useTranslation('settings');

  return (
    <section
      id="settings-appearance"
      aria-labelledby="settings-appearance-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h3 id="settings-appearance-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('preferences.title')}
        </h3>
        <div className="flex items-center gap-3">
          {prefsSaveSuccess && (
            <span className="flex items-center text-green-600 text-sm">
              <Check className="w-4 h-4 mr-1" /> {t('preferences.saved')}
            </span>
          )}
          {prefsSaveError && (
            <span className="flex items-center text-red-600 text-sm">
              <AlertCircle className="w-4 h-4 mr-1" /> {prefsSaveError}
            </span>
          )}
          <button
            onClick={onSave}
            disabled={prefsLoading}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium"
          >
            {prefsLoading ? t('security.saving') : t('preferences.saveAppearance')}
          </button>
        </div>
      </div>
      <div className="divide-y divide-gray-200">
        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-indigo-50 rounded-lg">
              <Globe className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.language')}</p>
              <p className="text-sm text-gray-500">{t('preferences.languageHelp')}</p>
            </div>
          </div>
          <select
            id="pref-ui-language"
            name="ui_language"
            aria-label={t('preferences.language')}
            value={preferences.ui_language}
            onChange={(event) => setPreferences((prev) => ({ ...prev, ui_language: event.target.value }))}
            className="block w-48 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
          >
            <option value="es-ES">{t('languages.es-ES')}</option>
            <option value="en-US">{t('languages.en-US')}</option>
          </select>
        </div>

        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-purple-50 rounded-lg">
              <Volume2 className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.voiceMode')}</p>
              <p className="text-sm text-gray-500">{t('preferences.voiceModeHelp')}</p>
            </div>
          </div>
          <Toggle
            id="pref-voice-mode-enabled"
            name="voice_mode_enabled"
            checked={preferences.voice_mode_enabled}
            label={t('preferences.voiceMode')}
            onChange={(checked) => setPreferences((prev) => ({ ...prev, voice_mode_enabled: checked }))}
          />
        </div>

        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-purple-50 rounded-lg">
              <Bell className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.notifications')}</p>
              <p className="text-sm text-gray-500">{t('preferences.notificationsHelp')}</p>
            </div>
          </div>
          <Toggle
            id="pref-notifications-enabled"
            name="notifications_enabled"
            checked={preferences.notifications_enabled}
            label={t('preferences.notifications')}
            onChange={(checked) => setPreferences((prev) => ({ ...prev, notifications_enabled: checked }))}
          />
        </div>

        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-gray-100 rounded-lg">
              <Moon className="w-5 h-5 text-gray-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.dark')}</p>
              <p className="text-sm text-gray-500">{t('preferences.darkHelp')}</p>
            </div>
          </div>
          <Toggle
            id="pref-dark-mode"
            name="dark_mode"
            checked={preferences.dark_mode}
            label={t('preferences.dark')}
            onChange={(checked) => setPreferences((prev) => ({ ...prev, dark_mode: checked }))}
          />
        </div>

        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-green-50 rounded-lg">
              <Clock className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.dwellTime')}</p>
              <p className="text-sm text-gray-500">{t('preferences.dwellTimeHelp')}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <input
              id="pref-dwell-time"
              name="dwell_time"
              type="range"
              min="0"
              max="2000"
              step="100"
              value={preferences.dwell_time}
              onChange={(event) =>
                setPreferences((prev) => ({ ...prev, dwell_time: parseInt(event.target.value) }))
              }
              className="w-32"
              aria-label={t('preferences.dwellTime')}
            />
            <span className="text-sm text-gray-600 w-16 text-right">{preferences.dwell_time}ms</span>
          </div>
        </div>

        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-orange-50 rounded-lg">
              <MousePointer className="w-5 h-5 text-orange-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.ignoreRepeats')}</p>
              <p className="text-sm text-gray-500">{t('preferences.ignoreRepeatsHelp')}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <input
              id="pref-ignore-repeats"
              name="ignore_repeats"
              type="range"
              min="0"
              max="2000"
              step="100"
              value={preferences.ignore_repeats}
              onChange={(event) =>
                setPreferences((prev) => ({ ...prev, ignore_repeats: parseInt(event.target.value) }))
              }
              className="w-32"
              aria-label={t('preferences.ignoreRepeats')}
            />
            <span className="text-sm text-gray-600 w-16 text-right">{preferences.ignore_repeats}ms</span>
          </div>
        </div>

        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-yellow-50 rounded-lg">
              <Eye className="w-5 h-5 text-yellow-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.highContrast')}</p>
              <p className="text-sm text-gray-500">{t('preferences.highContrastHelp')}</p>
            </div>
          </div>
          <Toggle
            id="pref-high-contrast"
            name="high_contrast"
            checked={preferences.high_contrast}
            label={t('preferences.highContrast')}
            onChange={(checked) => setPreferences((prev) => ({ ...prev, high_contrast: checked }))}
          />
        </div>
      </div>
    </section>
  );
}
