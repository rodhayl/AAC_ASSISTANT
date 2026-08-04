import type { Dispatch, SetStateAction } from 'react';
import { useEffect, useState } from 'react';
import { Circle, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../../lib/api';
import type { Preferences, VoiceStatus } from './types';

interface VoiceTabProps {
  preferences: Preferences;
  setPreferences: Dispatch<SetStateAction<Preferences>>;
  filteredVoices: SpeechSynthesisVoice[];
  showStatus: boolean;
}

export function VoiceTab({ preferences, setPreferences, filteredVoices, showStatus }: VoiceTabProps) {
  const { t } = useTranslation('settings');
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);

  useEffect(() => {
    if (!showStatus) return;
    const fetchVoiceStatus = async () => {
      try {
        const res = await api.get('/providers/voice-status');
        setVoiceStatus(res.data);
      } catch (err) {
        console.error('Failed to fetch voice dependency status', err);
      }
    };
    fetchVoiceStatus();
  }, [showStatus]);

  const voiceStatusItems = [
    {
      key: 'ffmpeg',
      label: t('ai.dependencies.ffmpeg.label'),
      help: t('ai.dependencies.ffmpeg.help'),
      link: 'https://ffmpeg.org/',
      status: voiceStatus?.ffmpeg?.installed ?? voiceStatus?.ffmpeg?.available,
      optional: true,
    },
    {
      key: 'stt',
      label: t('ai.dependencies.fasterWhisper.label'),
      help: t('ai.dependencies.fasterWhisper.help'),
      link: 'https://github.com/SYSTRAN/faster-whisper',
      status: voiceStatus?.stt?.installed ?? voiceStatus?.whisper?.installed,
      extra: voiceStatus?.stt?.model,
    },
    {
      key: 'tts',
      label: t('ai.dependencies.browserTts.label'),
      help: t('ai.dependencies.browserTts.help'),
      link: 'https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis',
      status: voiceStatus?.tts?.client_side === true,
      optional: true,
    },
  ];

  return (
    <section
      id="settings-voice"
      aria-labelledby="settings-voice-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <h3 id="settings-voice-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('preferences.tts')}
        </h3>
        <p className="text-sm text-gray-500 mt-1">{t('preferences.ttsHelp')}</p>
      </div>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-50 rounded-lg">
              <Volume2 className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="font-medium text-gray-900">{t('preferences.tts')}</p>
              <p className="text-sm text-gray-500">{t('preferences.ttsHelp')}</p>
            </div>
          </div>
          <select
            id="pref-tts-voice"
            name="tts_voice"
            aria-label={t('preferences.tts')}
            value={preferences.tts_voice}
            onChange={(event) => setPreferences((prev) => ({ ...prev, tts_voice: event.target.value }))}
            className="block w-48 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
          >
            <option value="default">{t('preferences.voices.default')}</option>
            {filteredVoices.length > 0 && <option disabled>──────────</option>}
            {filteredVoices.map((voice) => (
              <option key={voice.voiceURI} value={voice.voiceURI}>
                {voice.name} ({voice.lang})
              </option>
            ))}
          </select>
        </div>

        {showStatus && <div className="border-t border-gray-200 pt-6">
          <div className="flex items-center justify-between mb-2">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('ai.voiceDeps')}</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">{t('ai.voiceDepsHelp')}</p>
            </div>
          </div>
          <div className="space-y-3">
            {voiceStatusItems.map((item) => {
              const ok = item.status === true;
              return (
                <div
                  key={item.key}
                  className="flex items-center justify-between bg-gray-50 dark:bg-gray-900 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <Circle
                      className={`w-4 h-4 ${
                        ok ? 'text-green-500' : item.optional ? 'text-amber-500' : 'text-red-500'
                      }`}
                      fill={ok ? 'currentColor' : 'none'}
                    />
                    <div>
                      <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{item.label}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {ok ? t('ai.installed') : t('ai.notInstalled')} {item.extra ? `(${item.extra})` : ''}
                      </div>
                      {!ok && <div className="text-xs text-amber-600 dark:text-amber-400">{item.help}</div>}
                    </div>
                  </div>
                  <a
                    href={item.link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                    title={item.help}
                  >
                    {t('ai.howToInstall')}
                  </a>
                </div>
              );
            })}
          </div>
        </div>}
      </div>
    </section>
  );
}
