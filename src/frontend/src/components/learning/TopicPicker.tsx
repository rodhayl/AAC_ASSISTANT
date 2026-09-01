import { useMemo } from 'react';
import { CheckCircle2, History, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SymbolImage } from '../common/SymbolImage';
import { cn } from '../../lib/utils';

export interface PickerTopic {
  key: string;
  label: string;
  sublabel?: string;
  /** Value passed to startActivity as the session topic. */
  topic: string;
  /** Board/context label passed as the session purpose (saved topics). */
  purpose?: string;
  boardId?: number;
  practiced: boolean;
  imagePath?: string;
  emoji: string;
  /** Teacher who saved this topic; set when the pool mixes several teachers. */
  savedBy?: string;
}

export interface PickerRecentTopic {
  topic: string;
  purpose?: string;
  last_used_at?: string | null;
}

interface TopicPickerProps {
  topics: PickerTopic[];
  recent: PickerRecentTopic[];
  isStartingSession: boolean;
  onSelect: (topic: PickerTopic) => void;
  onContinueRecent: (topic: string, purpose?: string) => void;
  /** Hide the built-in title/subtitle; the host page supplies its own. */
  showTitle?: boolean;
}

function shuffle<T>(items: T[]): T[] {
  const copy = items.slice();
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

/**
 * Shuffle-bag ordering: topics not yet practiced come first (shuffled), then
 * practiced ones stay available but de-prioritized. Once every topic has been
 * practiced, the bag refills and all topics are fresh again.
 */
function orderByPractice(topics: PickerTopic[]): PickerTopic[] {
  const fresh = topics.filter((topic) => !topic.practiced);
  if (fresh.length === 0) {
    // Bag exhausted: refill — the whole pool is available again, fresh.
    return shuffle(topics.map((topic) => ({ ...topic, practiced: false })));
  }
  return [...shuffle(fresh), ...topics.filter((topic) => topic.practiced)];
}

function TopicCard({
  topic,
  isStartingSession,
  onSelect,
  showSavedBy = true,
}: {
  topic: PickerTopic;
  isStartingSession: boolean;
  onSelect: (topic: PickerTopic) => void;
  showSavedBy?: boolean;
}) {
  const { t } = useTranslation('learning');
  return (
    <button
      type="button"
      data-testid={`topic-card-${topic.key}`}
      onClick={() => onSelect(topic)}
      disabled={isStartingSession}
      className={cn(
        'group relative flex flex-col items-center gap-2 rounded-xl border border-border bg-background p-4 text-center transition-colors',
        'hover:border-brand hover:bg-surface-hover',
        'disabled:opacity-60 disabled:cursor-not-allowed',
        topic.practiced && 'opacity-80',
      )}
      aria-label={`${topic.label}${topic.sublabel ? ` (${topic.sublabel})` : ''}`}
    >
      {topic.practiced && (
        <span
          className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300"
          title={t('topicPicker.practiced')}
        >
          <CheckCircle2 className="h-3 w-3" />
          {t('topicPicker.practiced')}
        </span>
      )}
      <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-surface">
        {topic.imagePath ? (
          <SymbolImage imagePath={topic.imagePath} alt={topic.label} className="h-12 w-12 object-contain" />
        ) : (
          <span className="text-3xl" aria-hidden="true">{topic.emoji}</span>
        )}
      </div>
      <span className="text-sm font-semibold leading-tight text-foreground line-clamp-2">
        {topic.label}
      </span>
      {topic.sublabel && (
        <span className="text-[11px] leading-tight text-muted-foreground line-clamp-1">
          {topic.sublabel}
        </span>
      )}
      {showSavedBy && topic.savedBy && (
        <span className="text-[10px] leading-tight text-muted-foreground/80 line-clamp-1" title={topic.savedBy}>
          {t('topicPicker.savedBy', { teacher: topic.savedBy })}
        </span>
      )}
    </button>
  );
}

function TopicGrid({
  topics,
  isStartingSession,
  onSelect,
  showSavedBy,
}: {
  topics: PickerTopic[];
  isStartingSession: boolean;
  onSelect: (topic: PickerTopic) => void;
  showSavedBy?: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {topics.map((topic) => (
        <TopicCard
          key={topic.key}
          topic={topic}
          isStartingSession={isStartingSession}
          onSelect={onSelect}
          showSavedBy={showSavedBy}
        />
      ))}
    </div>
  );
}

export function TopicPicker({
  topics,
  recent,
  isStartingSession,
  onSelect,
  onContinueRecent,
  showTitle = true,
}: TopicPickerProps) {
  const { t } = useTranslation('learning');
  // Shuffle once per pool; stable across unrelated re-renders.
  const ordered = useMemo(() => orderByPractice(topics), [topics]);

  // When saved topics mix several teachers, group them under a per-teacher
  // heading (the cards then drop their inline label — the section says it).
  const groups = useMemo(() => {
    const teachers = Array.from(
      new Set(topics.map((topic) => topic.savedBy).filter((name): name is string => Boolean(name))),
    );
    if (teachers.length < 2) return null;
    return {
      common: ordered.filter((topic) => !topic.savedBy),
      teachers: teachers.map((teacher) => ({
        teacher,
        topics: orderByPractice(topics.filter((topic) => topic.savedBy === teacher)),
      })),
    };
  }, [ordered, topics]);

  return (
    <div className="mx-auto w-full max-w-2xl px-2 py-6 text-left">
      {showTitle && (
        <>
          <h2 className="text-lg font-semibold text-foreground">{t('topicPicker.title')}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('topicPicker.subtitle')}</p>
        </>
      )}

      {groups ? (
        <>
          <div className="mt-4">
            <TopicGrid
              topics={groups.common}
              isStartingSession={isStartingSession}
              onSelect={onSelect}
              showSavedBy={false}
            />
          </div>
          {groups.teachers.map((group) => (
            <div key={group.teacher} className="mt-6" data-testid={`topic-group-${group.teacher}`}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t('topicPicker.savedBy', { teacher: group.teacher })}
              </h3>
              <div className="mt-2">
                <TopicGrid
                  topics={group.topics}
                  isStartingSession={isStartingSession}
                  onSelect={onSelect}
                  showSavedBy={false}
                />
              </div>
            </div>
          ))}
        </>
      ) : (
        <div className="mt-4">
          <TopicGrid
            topics={ordered}
            isStartingSession={isStartingSession}
            onSelect={onSelect}
            showSavedBy
          />
        </div>
      )}

      {recent.length > 0 && (
        <div className="mt-6">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <History className="h-3.5 w-3.5" />
            {t('topicPicker.continue')}
          </h3>

          <div className="mt-2 flex flex-wrap gap-2">
            {recent.map((entry) => (
              <button
                key={`recent-${entry.topic}`}
                type="button"
                onClick={() => onContinueRecent(entry.topic, entry.purpose)}
                disabled={isStartingSession}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-sm text-foreground transition-colors hover:border-brand hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isStartingSession ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <span aria-hidden="true">▶</span>
                )}
                {entry.topic}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
