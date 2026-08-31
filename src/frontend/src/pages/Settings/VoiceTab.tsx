import type { Dispatch, SetStateAction } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Check, Circle, Loader2, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import api, { extractError } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { useTTSStore, type WarmupStatus } from '../../store/ttsStore';
import type { Preferences, VoiceStatus } from './types';

import { SectionTitle } from '@/components/ui/SectionTitle';

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

// Hover-to-speak delay options (ms). 1000 matches the schema default; the
// backend clamps persisted values to [0, 5000].
const HOVER_SPEAK_DELAY_OPTIONS = [500, 750, 1000, 1500, 2000, 3000, 5000];

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

function localVoiceLabel(voice: LocalVoiceEntry, t: TFunction): string {
  const parts = [voice.name];
  if (voice.region === 'american') parts.push(t('voice.americanEnglish'));
  else if (voice.region === 'british') parts.push(t('voice.britishEnglish'));
  parts.push(
    voice.gender === 'female'
      ? t('voice.female')
      : t('voice.male'),
  );
  return parts.join(' · ');
}

interface WarmupIndicatorProps {
  status: WarmupStatus;
  inProgressText: string;
  readyText: string;
  testId: string;
}

/** Inline badge showing the background pre-load status of a voice model. */
function WarmupIndicator({ status, inProgressText, readyText, testId }: WarmupIndicatorProps) {
  if (status !== 'warming' && status !== 'ready') return null;
  return (
    <div
      data-testid={testId}
      className="flex items-center gap-2 text-xs text-muted-foreground"
    >
      {status === 'warming' ? (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
          <span>{inProgressText}</span>
        </>
      ) : (
        <>
          <Check className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
          <span>{readyText}</span>
        </>
      )}
    </div>
  );
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
  const setLocalSpeed = useTTSStore((state) => state.setLocalSpeed);
  const ttsWarmupStatus = useTTSStore((state) => state.ttsWarmupStatus);
  const speechWarmupStatus = useTTSStore((state) => state.speechWarmupStatus);
  const vectorWarmupStatus = useTTSStore((state) => state.vectorWarmupStatus);
  const setTTSWarmupStatus = useTTSStore((state) => state.setTTSWarmupStatus);
  const setSpeechWarmupStatus = useTTSStore((state) => state.setSpeechWarmupStatus);

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

  // Keep the pre-load badges honest: voice-status reports the model's real
  // in-memory state, so align the badges with it. A model released after
  // warm-up (server restart / provider reset) drops a stale "ready" back to
  // idle instead of claiming the model is resident.
  useEffect(() => {
    if (!voiceStatus) return;
    const ttsLoaded = voiceStatus.tts_local?.model_loaded;
    if (typeof ttsLoaded === 'boolean') {
      const current = useTTSStore.getState().ttsWarmupStatus;
      if (ttsLoaded && current !== 'ready') setTTSWarmupStatus('ready');
      else if (!ttsLoaded && current === 'ready') setTTSWarmupStatus('idle');
    }
    const sttLoaded = voiceStatus.stt?.model_loaded;
    if (typeof sttLoaded === 'boolean') {
      const current = useTTSStore.getState().speechWarmupStatus;
      if (sttLoaded && current !== 'ready') setSpeechWarmupStatus('ready');
      else if (!sttLoaded && current === 'ready') setSpeechWarmupStatus('idle');
    }
  }, [voiceStatus, setTTSWarmupStatus, setSpeechWarmupStatus]);

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
      t('ai.installComplete'),
      t('ai.installFailed'),
    );
  };

  const installTTS = async () => {
    await runInstall(
      '/providers/tts/install',
      30 * 60 * 1000,
      t('ai.installComplete'),
      t('ai.installFailed'),
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
      setInstallMessage(t('ai.sttModelSaved'));
    } catch (err) {
      setInstallError(extractError(err, t('ai.sttModelSaveFailed')));
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
        <p className="text-sm font-medium text-foreground">
          {t('ai.localVoice')}
        </p>
        <p className="text-xs text-muted-foreground">
          {t('ai.localVoiceHelp')}
        </p>
      </div>
      <select
        id="pref-local-tts-voice"
        name="local_tts_voice"
        aria-label={t('ai.localVoice')}
        value={preferences.tts_local_voice}
        disabled={!localTTSAvailable}
        onChange={(event) => {
          setLocalVoice(event.target.value);
          setPreferences((prev) => ({ ...prev, tts_local_voice: event.target.value }));
        }}
        className="block w-72 pl-3 pr-10 py-2 text-base border-border focus:outline-none focus:ring-brand focus:border-brand sm:text-sm rounded-md disabled:cursor-not-allowed disabled:opacity-60"
      >
        <option value="default">{t('ai.voiceDefault')}</option>
        {groupedLocalVoices.map(([language, voices]) => (
          <optgroup key={language} label={`${languageLabel(language)} (${language})`}>
            {voices.map((voice) => (
              <option key={voice.name} value={voice.name}>
                {localVoiceLabel(voice, t)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );

  const LOCAL_SPEED_OPTIONS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0];

  const localSpeedPicker = (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-foreground">
          {t('ai.localSpeed')}
        </p>
        <p className="text-xs text-muted-foreground">
          {t('ai.localSpeedHelp')}
        </p>
      </div>
      <select
        id="pref-local-tts-speed"
        name="local_tts_speed"
        aria-label={t('ai.localSpeed')}
        value={String(preferences.tts_local_speed)}
        disabled={!localTTSAvailable}
        onChange={(event) => {
          const speed = parseFloat(event.target.value);
          setLocalSpeed(speed);
          setPreferences((prev) => ({ ...prev, tts_local_speed: speed }));
        }}
        className="block w-72 pl-3 pr-10 py-2 text-base border-border focus:outline-none focus:ring-brand focus:border-brand sm:text-sm rounded-md disabled:cursor-not-allowed disabled:opacity-60"
      >
        {LOCAL_SPEED_OPTIONS.map((speed) => (
          <option key={speed} value={String(speed)}>
            {speed}×{speed === 1.0 ? ` (${t('ai.speedNormal')})` : ''}
          </option>
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
      label: t('ai.dependencies.localTts.label'),
      help: t('ai.dependencies.localTts.help'),
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
      className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
    >
      <div className="flex items-center justify-between gap-4 border-b border-border p-6">
        <div>
        <h3 id="settings-voice-heading" className="text-lg font-semibold text-foreground">
          {t('preferences.tts')}
        </h3>
        <p className="text-sm text-muted-foreground mt-1">{t('preferences.ttsHelp')}</p>
        </div>
        {onSave && (
          <div className="flex shrink-0 items-center gap-3">
            {prefsSaveSuccess && (
              <span className="flex items-center text-sm text-green-600 dark:text-green-400">
                <Check className="mr-1 h-4 w-4" /> {t('preferences.saved')}
              </span>
            )}
            {prefsSaveError && (
              <span className="flex items-center text-sm text-red-600 dark:text-red-400">
                <AlertCircle className="mr-1 h-4 w-4" /> {prefsSaveError}
              </span>
            )}
            <Button
              type="button"
              onClick={() => { void onSave(); }}
              loading={prefsLoading}
            >
              {prefsLoading ? t('security.saving') : t('preferences.saveVoice')}
            </Button>
          </div>
        )}
      </div>
      <div className="p-6 space-y-6">
        <div className="rounded-xl border-2 border-brand/30 bg-brand/10 p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-surface p-2 shadow-sm">
              <Volume2 className="h-5 w-5 text-brand" />
            </div>
            <div className="min-w-0 flex-1">
              <h4 className="font-semibold text-foreground">{t('preferences.ttsEngine')}</h4>
              <p className="mt-1 text-sm text-muted-foreground">{t('preferences.ttsEngineHelp')}</p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <label htmlFor="pref-tts-provider" className="text-sm font-medium text-foreground">
                  {t('preferences.selectedEngine')}
                </label>
                <select
                  id="pref-tts-provider"
                  name="tts_provider"
                  aria-label={t('preferences.ttsEngine')}
                  value={preferences.tts_provider}
                  onChange={(event) => {
                    const provider = event.target.value as Preferences['tts_provider'];
                    setTTSProvider(provider);
                    setPreferences((prev) => ({ ...prev, tts_provider: provider }));
                  }}
                  className="block w-72 rounded-md border-border bg-surface py-2 pl-3 pr-10 text-base focus:border-brand focus:outline-none focus:ring-brand sm:text-sm "
                >
                  <option value="kokoro">{t('preferences.ttsProviders.kokoro')} — {t('preferences.defaultEngine')}</option>
                  <option value="browser">{t('preferences.ttsProviders.browser')}</option>
                </select>
              </div>
              <p className="mt-2 text-xs text-brand">{t('preferences.engineSingleChoiceHelp')}</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-border p-4 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-foreground">
                {t('preferences.hoverSpeak')}
              </p>
              <p className="text-xs text-muted-foreground">
                {t('preferences.hoverSpeakHelp')}
              </p>
            </div>
            <input
              id="pref-hover-speak-enabled"
              name="hover_speak_enabled"
              type="checkbox"
              aria-label={t('preferences.hoverSpeak')}
              checked={preferences.hover_speak_enabled}
              onChange={() =>
                setPreferences((prev) => ({
                  ...prev,
                  hover_speak_enabled: !prev.hover_speak_enabled,
                }))
              }
              className="h-5 w-5 rounded border-border text-brand focus:ring-brand"
            />
          </div>
          {preferences.hover_speak_enabled && (
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-foreground">
                  {t('preferences.hoverSpeakDelay')}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t('preferences.hoverSpeakDelayHelp')}
                </p>
              </div>
              <select
                id="pref-hover-speak-delay"
                name="hover_speak_delay_ms"
                aria-label={t('preferences.hoverSpeakDelay')}
                value={String(preferences.hover_speak_delay_ms)}
                onChange={(event) => {
                  // Capture eagerly: React restores the controlled DOM value
                  // after dispatch, so reading event.target inside the
                  // updater could observe the restored value.
                  const delay = parseInt(event.target.value, 10);
                  setPreferences((prev) => ({
                    ...prev,
                    hover_speak_delay_ms: delay,
                  }));
                }}
                className="block w-72 pl-3 pr-10 py-2 text-base border-border focus:outline-none focus:ring-brand focus:border-brand sm:text-sm rounded-md"
              >
                {HOVER_SPEAK_DELAY_OPTIONS.map((ms) => (
                  <option key={ms} value={String(ms)}>
                    {t('preferences.hoverSpeakDelaySeconds', { value: ms / 1000 })}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {preferences.tts_provider === 'browser' && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">{t('preferences.browserVoice')}</p>
              <p className="text-xs text-muted-foreground">{t('preferences.browserVoiceHelp')}</p>
            </div>
            <select
              id="pref-tts-voice"
              name="tts_voice"
              aria-label={t('preferences.browserVoice')}
              value={preferences.tts_voice}
              onChange={(event) => setPreferences((prev) => ({ ...prev, tts_voice: event.target.value }))}
              className="block w-56 pl-3 pr-10 py-2 text-base border-border focus:outline-none focus:ring-brand focus:border-brand sm:text-sm rounded-md"
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
              <div role="alert" className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-800 dark:text-red-200">
                {t('preferences.kokoroUnavailable')}
              </div>
            )}
            {localVoicePicker}
            {localSpeedPicker}
            <WarmupIndicator
              status={ttsWarmupStatus}
              inProgressText={t('ai.ttsWarmupInProgress')}
              readyText={t('ai.ttsWarmupReady')}
              testId="tts-warmup-indicator"
            />
          </>
        )}

        {showStatus && (
          <div className="border-t border-border pt-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-foreground">
                  {t('ai.sttModel')}
                </p>
              <p className="text-xs text-muted-foreground">
                {t('ai.sttModelHelp')}
              </p>
              </div>
              <select
                id="stt-model"
                name="stt_model"
                aria-label={t('ai.sttModel')}
                value={sttModel}
                disabled={Object.keys(sttModels).length === 0 || sttModelSaving}
                onChange={(event) => { void saveSttModel(event.target.value); }}
                className="block w-72 pl-3 pr-10 py-2 text-sm border-border rounded-md disabled:cursor-not-allowed disabled:opacity-60"
              >
                {Object.entries(sttModels).map(([model, details]) => (
                  <option key={model} value={model}>
                    {model} — {details.description} ({details.size})
                  </option>
                ))}
              </select>
            </div>
            <WarmupIndicator
              status={speechWarmupStatus}
              inProgressText={t('ai.speechWarmupInProgress')}
              readyText={t('ai.speechWarmupReady')}
              testId="speech-warmup-indicator"
            />
            <div className="mt-4">
              <WarmupIndicator
                status={vectorWarmupStatus}
                inProgressText={t('ai.vectorWarmupInProgress')}
                readyText={t('ai.vectorWarmupReady')}
                testId="vector-warmup-indicator"
              />
            </div>
          </div>
        )}

        {showStatus && <div className="border-t border-border pt-6">
          <div className="flex items-center justify-between mb-2">
            <div>
              <SectionTitle as="h3">{t('ai.voiceDeps')}</SectionTitle>
              <p className="text-sm text-muted-foreground">{t('ai.voiceDepsHelp')}</p>
            </div>
          </div>
          <div className="space-y-3">
            {voiceStatusItems.map((item) => {
              const ok = item.status === true;
              return (
                <div
                  key={item.key}
                  className="flex items-center justify-between bg-background rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <Circle
                      className={`w-4 h-4 ${
                        ok ? 'text-green-500' : item.optional ? 'text-amber-500' : 'text-red-500'
                      }`}
                      fill={ok ? 'currentColor' : 'none'}
                    />
                    <div>
                      <div className="text-sm font-semibold text-foreground">{item.label}</div>
                      <div className="text-xs text-muted-foreground">
                        {ok ? t('ai.installed') : t('ai.notInstalled')} {item.extra ? `(${item.extra})` : ''}
                      </div>
                      {!ok && <div className="text-xs text-amber-800 dark:text-amber-300 font-medium">{item.help}</div>}
                      {!ok && item.key === 'stt' && voiceStatus?.actions?.install_voice?.reason && (
                        <div className="text-xs text-muted-foreground">
                          {voiceStatus.actions.install_voice.reason}
                        </div>
                      )}
                    </div>
                  </div>
                  {!ok && item.key === 'stt' && voiceStatus?.actions?.install_voice?.supported ? (
                    <Button
                      type="button"
                      size="sm"
                      onClick={installVoiceDependencies}
                      disabled={installingVoiceDeps || voiceStatus.actions.install_voice.in_progress}
                      title={item.help}
                    >
                      {installingVoiceDeps || voiceStatus.actions.install_voice.in_progress
                        ? t('ai.installing')
                        : t('ai.installAutomatically')}
                    </Button>
                  ) : !ok && item.key === 'tts_local' && voiceStatus?.actions?.install_tts?.supported ? (
                    <Button
                      type="button"
                      size="sm"
                      onClick={installTTS}
                      disabled={installingVoiceDeps || voiceStatus.actions.install_tts.in_progress}
                      title={item.help}
                    >
                      {installingVoiceDeps || voiceStatus.actions.install_tts.in_progress
                        ? t('ai.installing')
                        : t('ai.installAutomatically')}
                    </Button>
                  ) : (
                    <a
                      href={item.link}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-brand hover:underline"
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
