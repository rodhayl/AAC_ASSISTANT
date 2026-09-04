import { useCallback, useEffect, useState } from 'react';
import { Check, Shield, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../store/toastStore';
import api, { extractError } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { FormLabel } from '../../components/ui/FormLabel';

interface SafetyEvent {
  id: number;
  surface: string;
  direction: string;
  verdict: string;
  matched: string[];
  detail: string | null;
  created_at: string | null;
}

interface GlobalPolicy {
  level: 'strict' | 'standard' | 'relaxed';
  forbidden_topics: string[];
  trigger_words: string[];
  feature_locks: Record<string, boolean>;
  sentinel_moderation: boolean;
  max_response_length: number | null;
  locked_fields: string[];
}

const FEATURE_LOCK_KEYS: Array<{ key: string; labelKey: string }> = [
  { key: 'block_ai_chat', labelKey: 'lockChat' },
  { key: 'block_board_ai', labelKey: 'lockBoardAI' },
  { key: 'block_custom_topics', labelKey: 'lockCustomTopics' },
  { key: 'block_autogen_pictograms', labelKey: 'lockAutogen' },
  { key: 'block_social_messaging', labelKey: 'lockSocial' },
];

function linesToArray(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function arrayToLines(value: string[] | undefined): string {
  return (value ?? []).join('\n');
}

export function ContentSafetyTab() {
  const { t } = useTranslation('settings');
  const addToast = useToastStore((state) => state.addToast);
  const [policy, setPolicy] = useState<GlobalPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [events, setEvents] = useState<SafetyEvent[]>([]);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purging, setPurging] = useState(false);

  const [textValues, setTextValues] = useState<Record<string, string>>({});

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const policyRes = await api.get('/settings/content-safety');
      setPolicy(policyRes.data);
      setTextValues({
        forbidden_topics: arrayToLines(policyRes.data.forbidden_topics),
        trigger_words: arrayToLines(policyRes.data.trigger_words),
        locked_fields: arrayToLines(policyRes.data.locked_fields),
      });
      try {
        const eventsRes = await api.get('/settings/content-safety/events');
        setEvents(eventsRes.data || []);
      } catch {
        setEvents([]);
      }
    } catch (err) {
      addToast(extractError(err, t('contentSafety.saveFailed')), 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast, t]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  if (loading) {
    return (
      <section
        id="settings-content-safety"
        aria-labelledby="settings-content-safety-heading"
        className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
      >
        <div className="p-6 border-b border-border">
          <h3 id="settings-content-safety-heading" className="text-lg font-semibold text-foreground">
            {t('contentSafety.title')}
          </h3>
        </div>
        <div className="p-6 text-sm text-muted-foreground">{t('learningModes.loading')}</div>
      </section>
    );
  }

  if (!policy) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      const filtered: Record<string, unknown> = {
        level: policy.level,
        forbidden_topics: linesToArray(textValues.forbidden_topics),
        trigger_words: linesToArray(textValues.trigger_words),
        feature_locks: policy.feature_locks,
        sentinel_moderation: policy.sentinel_moderation,
        max_response_length:
          policy.max_response_length === null || policy.max_response_length <= 0
            ? null
            : policy.max_response_length,
        locked_fields: linesToArray(textValues.locked_fields),
      };
      const res = await api.put<GlobalPolicy>('/settings/content-safety', filtered);
      const next = res.data;
      setPolicy(next);
      setTextValues({
        forbidden_topics: arrayToLines(next.forbidden_topics),
        trigger_words: arrayToLines(next.trigger_words),
        locked_fields: arrayToLines(next.locked_fields),
      });
      addToast(t('contentSafety.saved'), 'success');
    } catch (err) {
      addToast(extractError(err, t('contentSafety.saveFailed')), 'error');
    } finally {
      setSaving(false);
    }
  };

  const setField = <K extends keyof GlobalPolicy>(key: K, value: GlobalPolicy[K]) => {
    setPolicy((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const setLock = (key: string, value: boolean) => {
    setPolicy((prev) =>
      prev ? { ...prev, feature_locks: { ...prev.feature_locks, [key]: value } } : prev,
    );
  };

  const setText = (key: string, value: string) => {
    setTextValues((prev) => ({ ...prev, [key]: value }));
  };

  const purgeSymbols = async () => {
    setPurging(true);
    try {
      const res = await api.delete('/settings/content-safety/ai-symbols');
      addToast(t('contentSafety.purgeDone', { count: res.data?.deleted ?? 0 }), 'success');
      setPurgeOpen(false);
    } catch (err) {
      addToast(extractError(err, t('contentSafety.saveFailed')), 'error');
    } finally {
      setPurging(false);
    }
  };

  const clearEvents = async () => {
    try {
      await api.delete('/settings/content-safety/events');
      setEvents([]);
      addToast(t('contentSafety.eventsCleared'), 'success');
    } catch (err) {
      addToast(extractError(err, t('contentSafety.saveFailed')), 'error');
    }
  };

  return (
    <section
      id="settings-content-safety"
      aria-labelledby="settings-content-safety-heading"
      className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
    >
      <div className="p-6 border-b border-border flex items-center gap-3">
        <Shield className="w-5 h-5 text-brand" />
        <div>
          <h3 id="settings-content-safety-heading" className="text-lg font-semibold text-foreground">
            {t('contentSafety.title')}
          </h3>
          <p className="text-sm text-muted-foreground mt-1">{t('contentSafety.subtitle')}</p>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Filter level */}
        <div>
          <FormLabel htmlFor="content-safety-level">{t('contentSafety.level')}</FormLabel>
          <select
            id="content-safety-level"
            value={policy.level}
            onChange={(event) => setField('level', event.target.value as GlobalPolicy['level'])}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground focus:ring-2 focus:ring-brand sm:w-64"
          >
            <option value="strict">{t('contentSafety.strict')}</option>
            <option value="standard">{t('contentSafety.standard')}</option>
            <option value="relaxed">{t('contentSafety.relaxed')}</option>
          </select>
          <p className="text-xs text-muted-foreground mt-1.5">{t('contentSafety.levelHelp')}</p>
        </div>

        {/* Forbidden topics + trigger words */}
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <FormLabel htmlFor="content-safety-forbidden-topics">
              {t('contentSafety.forbiddenTopics')}
            </FormLabel>
            <textarea
              id="content-safety-forbidden-topics"
              value={textValues.forbidden_topics ?? ''}
              onChange={(event) => setText('forbidden_topics', event.target.value)}
              rows={4}
              className="w-full p-2 border border-border rounded-lg font-mono text-sm"
              placeholder="astronomía"
            />
            <p className="text-xs text-muted-foreground mt-1">{t('contentSafety.forbiddenTopicsHelp')}</p>
          </div>
          <div>
            <FormLabel htmlFor="content-safety-trigger-words">
              {t('contentSafety.triggerWords')}
            </FormLabel>
            <textarea
              id="content-safety-trigger-words"
              value={textValues.trigger_words ?? ''}
              onChange={(event) => setText('trigger_words', event.target.value)}
              rows={4}
              className="w-full p-2 border border-border rounded-lg font-mono text-sm"
              placeholder="guerra"
            />
            <p className="text-xs text-muted-foreground mt-1">{t('contentSafety.triggerWordsHelp')}</p>
          </div>
        </div>

        {/* Feature locks */}
        <div>
          <FormLabel>{t('contentSafety.featureLocks')}</FormLabel>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {FEATURE_LOCK_KEYS.map(({ key, labelKey }) => (
              <label
                key={key}
                className="flex items-start gap-2 text-sm text-foreground cursor-pointer bg-muted/40 border border-border rounded-lg px-3 py-2"
              >
                <input
                  type="checkbox"
                  checked={Boolean(policy.feature_locks[key])}
                  onChange={(event) => setLock(key, event.target.checked)}
                  className="mt-0.5 w-4 h-4 accent-brand"
                />
                <span>{t(`contentSafety.${labelKey}`)}</span>
              </label>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-1.5">{t('contentSafety.featureLocksHelp')}</p>
        </div>

        {/* Sentinel + max length */}
        <div className="grid gap-6 sm:grid-cols-2">
          <label className="flex items-start gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={policy.sentinel_moderation}
              onChange={(event) => setField('sentinel_moderation', event.target.checked)}
              className="mt-0.5 w-4 h-4 accent-brand"
            />
            <span>
              <span className="font-medium">{t('contentSafety.sentinel')}</span>
              <span className="block text-xs text-muted-foreground mt-0.5">{t('contentSafety.sentinelHelp')}</span>
            </span>
          </label>
          <div>
            <FormLabel htmlFor="content-safety-max-length">{t('contentSafety.maxLength')}</FormLabel>
            <input
              id="content-safety-max-length"
              type="number"
              min={0}
              value={policy.max_response_length ?? ''}
              onChange={(event) =>
                setField(
                  'max_response_length',
                  event.target.value === '' ? null : Math.max(0, Number(event.target.value)),
                )
              }
              className="w-full p-2 border border-border rounded-lg"
            />
            <p className="text-xs text-muted-foreground mt-1">{t('contentSafety.maxLengthHelp')}</p>
          </div>
        </div>

        {/* Locked fields for teachers */}
        <div>
          <FormLabel htmlFor="content-safety-locked-fields">{t('contentSafety.lockedFields')}</FormLabel>
          <textarea
            id="content-safety-locked-fields"
            value={textValues.locked_fields ?? ''}
            onChange={(event) => setText('locked_fields', event.target.value)}
            rows={3}
            className="w-full p-2 border border-border rounded-lg font-mono text-sm"
            placeholder={'block_ai_chat\nblock_board_ai'}
          />
          <p className="text-xs text-muted-foreground mt-1">{t('contentSafety.lockedFieldsHelp')}</p>
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={handleSave} loading={saving}>
            <Check className="w-4 h-4 mr-2" />
            {saving ? t('contentSafety.saving') : t('contentSafety.save')}
          </Button>
        </div>

        {/* Event log */}
        <div className="border-t border-border pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-semibold text-foreground">{t('contentSafety.events')}</h4>
              <p className="text-xs text-muted-foreground mt-0.5">{t('contentSafety.eventsHelp')}</p>
            </div>
            {events.length > 0 && (
              <button
                type="button"
                onClick={() => { void clearEvents(); }}
                className="flex items-center gap-1.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg px-3 py-1.5"
              >
                <Trash2 className="w-4 h-4" />
                {t('contentSafety.clearEvents')}
              </button>
            )}
          </div>
          {events.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">{t('contentSafety.noEvents')}</p>
          ) : (
            <div className="mt-3 overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-2 font-medium">{t('contentSafety.surface')}</th>
                    <th className="px-3 py-2 font-medium">{t('contentSafety.direction')}</th>
                    <th className="px-3 py-2 font-medium">{t('contentSafety.verdict')}</th>
                    <th className="px-3 py-2 font-medium">{t('contentSafety.matched')}</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.id} className="border-t border-border">
                      <td className="px-3 py-2">{event.surface}</td>
                      <td className="px-3 py-2">{t(`contentSafety.${event.direction}`)}</td>
                      <td className="px-3 py-2 capitalize">{t(`contentSafety.${event.verdict}`)}</td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {(event.matched ?? []).join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Purge AI symbols */}
        <div className="border-t border-border pt-6 flex items-start justify-between gap-4">
          <div>
            <h4 className="font-semibold text-foreground text-red-600 dark:text-red-400">
              {t('contentSafety.purge')}
            </h4>
            <p className="text-xs text-muted-foreground mt-0.5">{t('contentSafety.purgeHelp')}</p>
          </div>
          <button
            type="button"
            onClick={() => setPurgeOpen(true)}
            className="flex items-center gap-1.5 text-sm bg-red-600 text-white rounded-lg px-3 py-2 hover:bg-red-700"
          >
            <Trash2 className="w-4 h-4" />
            {t('contentSafety.purge')}
          </button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={purgeOpen}
        onClose={() => setPurgeOpen(false)}
        onConfirm={purgeSymbols}
        title={t('contentSafety.purge')}
        description={t('contentSafety.purgeConfirm')}
        confirmText={t('contentSafety.purge')}
        cancelText={t('profile.cancel')}
        variant="danger"
        isLoading={purging}
      />
    </section>
  );
}