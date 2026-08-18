import type { Dispatch, SetStateAction } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Check, Circle, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api, { extractError } from '../../lib/api';
import { useTTSStore } from '../../store/ttsStore';
import type { Preferences, VoiceStatus } from './types';

interface VoiceTabProps {
  preferences: Preferences;
  setPreferences: Dispatch<SetStateAction<Preferences>>;
  filteredVoices: SpeechSynthesisVoice[];
  showStatus: boolean;
  prefsLoading?: boolean;
  prefsSaveSuccess?: boolean;
  prefsSaveError?: string | null;
  onSave?: () => Promise<void>;
}

type LocalVoiceEntry = {
  name: string;
  language: string;
  gender: string;
  region?: string | null;
};

const LANGUAGE_LABELS: Record<string, string> = {
  es: 'Español',
  en: 'English',
  fr: 'Français',
  it: 'Italiano',
  pt: 'Português',
  ja: '日本語',
  zh: '中文',
};

function languageLabel(code: string): string {
  return LANGUAGE_LABELS[code] || code;
}

function localVoiceLabel(voice: LocalVoiceEntry): string {
  const parts = [voice.name];
  if (voice.region === 'american') parts.push('American English');
  else if (voice.region === 'british') parts.push('British English');
  parts.push(voice.gender === 'female' ? 'Female' : 'Male');
  return parts.join(' · ');
}

export function VoiceTab({
  preferences,
  setPreferences,
  filteredVoices,
  showStatus,
  prefsLoading = false,
  prefsSaveSuccess = false,
  prefsSaveError = null,
  onSave,
}: VoiceTabProps) {
  const { t } = useTranslation('settings');
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [installingVoiceDeps, setInstallingVoiceDeps] = useState(false);
  const [installMessage, setInstallMessage] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [sttModelSaving, setSttModelSaving] = useState(false);
  const setTTSProvider = useTTSStore((state) => state.setTTSProvider);
  const setLocalVoice = useTTSStore((state) => state.setLocalVoice);

  const fetchVoiceStatus = useCallback(async () => {
    const res = await api.get('/providers/voice-status');
    setVoiceStatus(res.data);
  }, []);

  useEffect(() => {
    const loadVoiceStatus = async () => {
      try {
        await fetchVoiceStatus();
      } catch (err) {
        console.error('Failed to fetch voice dependency status', err);
      }
    };
    loadVoiceStatus();
  }, [fetchVoiceStatus, showStatus]);

  // Both "install" flows share the same shape: flag the busy state, clear
  // prior messages, POST to the installer, then refresh the dependency status.
  const runInstall = async (
    endpoint: string,
    timeoutMs: number,
    fallbackMessage: string,
    fallbackError: string,
  ) => {
    setInstallingVoiceDeps(true);
    setInstallMessage(null);
    setInstallError(null);
    try {
      const res = await api.post(endpoint, {}, { timeout: timeoutMs });
      setInstallMessage(res.data?.message || fallbackMessage);
      await fetchVoiceStatus();
    } catch (err) {
      setInstallError(extractError(err, fallbackError));
    } finally {
      setInstallingVoiceDeps(false);
    }
  };

  const installVoiceDependencies = async () => {
    await runInstall(
      '/providers/voice/install',
      10 * 60 * 1000,
      t('ai.installComplete', 'Voice dependencies installed.'),
      t('ai.installFailed', 'Automatic voice installation failed.'),
    );
  };

  const installTTS = async () => {
    await runInstall(
      '/providers/tts/install',
      30 * 60 * 1000,
      t('ai.installComplete', 'Local neural TTS installed.'),
      t('ai.installFailed', 'Automatic TTS installation failed.'),
    );
  };

  const localTTSAvailable = voiceStatus?.tts_local?.available === true;
  const sttModel = voiceStatus?.stt?.model || 'tiny';
  const sttModels = voiceStatus?.stt?.models || {};

  const saveSttModel = async (model: string) => {
    setSttModelSaving(true);
    setInstallError(null);
    try {
      await api.put('/providers/stt/model', { model });
      await fetchVoiceStatus();
      setInstallMessage(t('ai.sttModelSaved', 'Speech-to-text model updated.'));
    } catch (err) {
      setInstallError(extractError(err, t('ai.sttModelSaveFailed', 'Could not update the speech-to-text model.')));
    } finally {
      setSttModelSaving(false);
    }
  };
  const groupedLocalVoices = useMemo(() => {
    const groups = new Map<string, LocalVoiceEntry[]>();
    for (const voice of voiceStatus?.tts_local?.voices || []) {
      const list = groups.get(voice.language) || [];
      list.push(voice);
      groups.set(voice.language, list);
    }
    return Array.from(groups.entries());
  }, [voiceStatus?.tts_local?.voices]);

  const localVoicePicker = (
    <div className="flex items-center justify-between gap-4">
          <div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('ai.localVoice', 'Local neural voice')}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {t('ai.localVoiceHelp', 'Pick a specific Kokoro voice. Its language is used for synthesis, so choose one matching the language you speak.')}
        </p>
      </div>
      <select
        id="pref-local-tts-voice"
        name="local_tts_voice"
        aria-label={t('ai.localVoice', 'Local neural voice')}
        value={preferences.tts_local_voice}
        disabled={!localTTSAvailable}
        onChange={(event) => {
          setLocalVoice(event.target.value);
          setPreferences((prev) => ({ ...prev, tts_local_voice: event.target.value }));
        }}
        className="block w-72 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md disabled:cursor-not-allowed disabled:opacity-60"
      >
        <option value="default">{t('ai.voiceDefault', 'Default (auto)')}</option>
        {groupedLocalVoices.map(([language, voices]) => (
          <optgroup key={language} label={`${languageLabel(language)} (${language})`}>
            {voices.map((voice) => (
              <option key={voice.name} value={voice.name}>
                {localVoiceLabel(voice)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );

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
    {
      key: 'tts_local',
      label: t('ai.dependencies.localTts.label', 'Local neural voice (Kokoro)'),
      help: t('ai.dependencies.localTts.help', 'Natural multi-language speech that runs locally on your computer.'),
      link: 'https://github.com/thewh1teagle/kokoro-onnx',
      status: localTTSAvailable,
      optional: false,
      extra: voiceStatus?.tts_local?.model_size_mb ? `~${voiceStatus.tts_local.model_size_mb} MB` : undefined,
    },
  ];

  return (
    <section
      id="settings-voice"
      aria-labelledby="settings-voice-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="flex items-center justify-between gap-4 border-b border-gray-200 p-6 dark:border-gray-700">
        <div>
        <h3 id="settings-voice-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('preferences.tts')}
        </h3>
        <p className="text-sm text-gray-500 mt-1">{t('preferences.ttsHelp')}</p>
        </div>
        {onSave && (
          <div className="flex shrink-0 items-center gap-3">
            {prefsSaveSuccess && (
              <span className="flex items-center text-sm text-green-600">
                <Check className="mr-1 h-4 w-4" /> {t('preferences.saved')}
              </span>
            )}
            {prefsSaveError && (
              <span className="flex items-center text-sm text-red-600">
                <AlertCircle className="mr-1 h-4 w-4" /> {prefsSaveError}
              </span>
            )}
            <button
              type="button"
              onClick={() => { void onSave(); }}
              disabled={prefsLoading}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {prefsLoading ? t('security.saving') : t('preferences.saveVoice')}
            </button>
          </div>
        )}
      </div>
      <div className="p-6 space-y-6">
        <div className="rounded-xl border-2 border-indigo-100 bg-indigo-50/50 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-white p-2 shadow-sm dark:bg-gray-800">
              <Volume2 className="h-5 w-5 text-indigo-600" />
            </div>
            <div className="min-w-0 flex-1">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100">{t('preferences.ttsEngine', 'Voice output engine')}</h4>
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{t('preferences.ttsEngineHelp', 'Choose one engine for spoken panels and messages.')}</p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <label htmlFor="pref-tts-provider" className="text-sm font-medium text-gray-700 dark:text-gray-200">
                  {t('preferences.selectedEngine', 'Selected engine')}
                </label>
                <select
                  id="pref-tts-provider"
                  name="tts_provider"
                  aria-label={t('preferences.ttsEngine', 'Voice output engine')}
                  value={preferences.tts_provider}
                  onChange={(event) => {
                    const provider = event.target.value as Preferences['tts_provider'];
                    setTTSProvider(provider);
                    setPreferences((prev) => ({ ...prev, tts_provider: provider }));
                  }}
                  className="block w-72 rounded-md border-gray-300 bg-white py-2 pl-3 pr-10 text-base focus:border-indigo-500 focus:outline-none focus:ring-indigo-500 sm:text-sm dark:bg-gray-800"
                >
                  <option value="kokoro">{t('preferences.ttsProviders.kokoro', 'Kokoro (local neural voice)')} — {t('preferences.defaultEngine', 'default')}</option>
                  <option value="browser">{t('preferences.ttsProviders.browser', 'Browser / system voice')}</option>
                </select>
              </div>
              <p className="mt-2 text-xs text-indigo-800 dark:text-indigo-200">{t('preferences.engineSingleChoiceHelp', 'Only this engine speaks. Browser voice is used only when you explicitly select it.')}</p>
            </div>
          </div>
        </div>

        {preferences.tts_provider === 'browser' && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('preferences.browserVoice', 'Browser voice')}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('preferences.browserVoiceHelp', 'Uses voices installed by your browser or operating system.')}</p>
            </div>
            <select
              id="pref-tts-voice"
              name="tts_voice"
              aria-label={t('preferences.browserVoice', 'Browser voice')}
              value={preferences.tts_voice}
              onChange={(event) => setPreferences((prev) => ({ ...prev, tts_voice: event.target.value }))}
              className="block w-56 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
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
        )}

        {preferences.tts_provider === 'kokoro' && (
          <>
            {!localTTSAvailable && (
              <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                {t('preferences.kokoroUnavailable', 'Kokoro is not ready. Restart start.sh to install and prepare the local voice runtime.')}
              </div>
            )}
            {localVoicePicker}
          </>
        )}

        {showStatus && (
          <div className="border-t border-gray-200 pt-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('ai.sttModel', 'Speech-to-text model')}
                </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t('ai.sttModelHelp', 'Whisper-tiny is the fast 39M-parameter default. Tiny is bundled with the installer; other sizes download on first use.')}
              </p>
              </div>
              <select
                id="stt-model"
                name="stt_model"
                aria-label={t('ai.sttModel', 'Speech-to-text model')}
                value={sttModel}
                disabled={Object.keys(sttModels).length === 0 || sttModelSaving}
                onChange={(event) => { void saveSttModel(event.target.value); }}
                className="block w-72 pl-3 pr-10 py-2 text-sm border-gray-300 rounded-md disabled:cursor-not-allowed disabled:opacity-60"
              >
                {Object.entries(sttModels).map(([model, details]) => (
                  <option key={model} value={model}>
                    {model} — {details.description} ({details.size})
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

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
                      {!ok && <div className="text-xs text-amber-800 dark:text-amber-300 font-medium">{item.help}</div>}
                      {!ok && item.key === 'stt' && voiceStatus?.actions?.install_voice?.reason && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          {voiceStatus.actions.install_voice.reason}
                        </div>
                      )}
                    </div>
                  </div>
                  {!ok && item.key === 'stt' && voiceStatus?.actions?.install_voice?.supported ? (
                    <button
                      type="button"
                      onClick={installVoiceDependencies}
                      disabled={installingVoiceDeps || voiceStatus.actions.install_voice.in_progress}
                      className="rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                      title={item.help}
                    >
                      {installingVoiceDeps || voiceStatus.actions.install_voice.in_progress
                        ? t('ai.installing', 'Installing...')
                        : t('ai.installAutomatically', 'Install automatically')}
                    </button>
                  ) : !ok && item.key === 'tts_local' && voiceStatus?.actions?.install_tts?.supported ? (
                    <button
                      type="button"
                      onClick={installTTS}
                      disabled={installingVoiceDeps || voiceStatus.actions.install_tts.in_progress}
                      className="rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                      title={item.help}
                    >
                      {installingVoiceDeps || voiceStatus.actions.install_tts.in_progress
                        ? t('ai.installing', 'Installing...')
                        : t('ai.installAutomatically', 'Install automatically')}
                    </button>
                  ) : (
                    <a
                      href={item.link}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                      title={item.help}
                    >
                      {t('ai.howToInstall')}
                    </a>
                  )}
                </div>
              );
            })}
          </div>
          {installMessage && (
            <p className="mt-3 text-sm text-green-700 dark:text-green-400">{installMessage}</p>
          )}
          {installError && (
            <p className="mt-3 text-sm text-red-700 dark:text-red-400">{installError}</p>
          )}
        </div>}
      </div>
    </section>
  );
}
