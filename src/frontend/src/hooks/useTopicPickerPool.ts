import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../store/authStore';
import { useLearningStore } from '../store/learningStore';
import api from '../lib/api';
import { loadTopicsForUser, type SavedTopic } from '../lib/learningTopics';
import { dedupeLearningSymbols } from '../lib/symbols';
import {
  COMMON_TOPIC_KEYS,
  TOPIC_CANONICAL_NAME,
  TOPIC_EMOJI,
  findTopicPictogram,
  normalizeTopic,
  type CommonTopicKey,
} from '../lib/topicCatalog';
import type { PickerRecentTopic, PickerTopic } from '../components/learning/TopicPicker';
import type { LearningSymbolItem } from '../types';

interface TopicPoolResponse {
  common?: Array<{ key: string; practiced?: boolean; last_used_at?: string | null }>;
  recent?: Array<{ topic: string; purpose?: string; last_used_at?: string | null; count?: number }>;
}

/**
 * Shared topic-picker pool for the Learning page and the Communication tab's
 * boardless topic conversations.
 *
 * Owns: the backend topic pool + practice coverage, the teacher/admin's
 * saved topics (localStorage), and the symbol library used to resolve card
 * pictograms. The pool refreshes whenever a session ends so the topic just
 * practiced is marked and de-prioritized next time.
 */
export function useTopicPickerPool() {
  const { t, i18n } = useTranslation('learning');
  const user = useAuthStore((state) => state.user);
  const currentSession = useLearningStore((state) => state.currentSession);
  const [topicPool, setTopicPool] = useState<TopicPoolResponse | null>(null);
  const [savedTopics, setSavedTopics] = useState<SavedTopic[]>([]);
  const [symbolItems, setSymbolItems] = useState<LearningSymbolItem[]>([]);
  const [symbolLang, setSymbolLang] = useState('');
  const [symbolLoading, setSymbolLoading] = useState(false);

  const currentLang = i18n?.language?.split('-')[0] || 'en';
  const symbolLanguage = currentLang === 'es' ? 'es' : 'en';

  useEffect(() => {
    if (!user?.id) return;
    let cancelled = false;
    const canManage = user.user_type === 'teacher' || user.user_type === 'admin';
    void loadTopicsForUser(user.id, canManage)
      .then((topics) => {
        if (!cancelled) setSavedTopics(topics);
      })
      .catch(() => {
        // The picker falls back to an empty saved list; never block on it.
        if (!cancelled) setSavedTopics([]);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id, user?.user_type]);

  const fetchTopicPool = useCallback(async () => {
    if (!user?.id) return;
    try {
      const response = await api.get('/learning/topics', { params: { user_id: user.id } });
      setTopicPool(response.data && typeof response.data === 'object' ? response.data : null);
    } catch {
      // The picker falls back to a full fresh pool; never block learning on it.
      setTopicPool(null);
    }
  }, [user?.id]);

  useEffect(() => {
    void fetchTopicPool();
  }, [fetchTopicPool]);

  const fetchSymbols = useCallback(async () => {
    setSymbolLoading(true);
    try {
      const response = await api.get('/boards/symbols', {
        params: { limit: 1000, language: symbolLanguage },
      });
      setSymbolItems(dedupeLearningSymbols(response.data || []));
      setSymbolLang(symbolLanguage);
    } catch {
      setSymbolItems([]);
    } finally {
      setSymbolLoading(false);
    }
  }, [symbolLanguage]);

  // Prefetch the symbol library on mount and keep it aligned with the active
  // language so card pictograms never wait for a fetch.
  useEffect(() => {
    void fetchSymbols();
  }, [fetchSymbols]);

  // When a session ends the picker returns; refresh coverage so the topic
  // just practiced is marked and de-prioritized next time.
  const hadSessionRef = useRef(false);
  useEffect(() => {
    const hasSession = Boolean(currentSession);
    if (hadSessionRef.current && !hasSession) {
      void fetchTopicPool();
    }
    hadSessionRef.current = hasSession;
  }, [currentSession, fetchTopicPool]);

  // Picker pool: the nine canonical topics (always available, coverage from
  // the backend) plus the teacher/admin's saved topics (coverage matched
  // against recently used sessions). Pictograms come from the symbol library;
  // every card keeps an emoji fallback so the pool is never blank.
  const pickerTopics = useMemo<PickerTopic[]>(() => {
    const practicedByKey = new Map(
      (topicPool?.common ?? []).map((entry) => [entry.key, Boolean(entry.practiced)]),
    );
    const recentByTopic = new Map<string, { purpose?: string }>();
    for (const entry of topicPool?.recent ?? []) {
      recentByTopic.set(normalizeTopic(entry.topic), { purpose: entry.purpose });
    }

    const common: PickerTopic[] = COMMON_TOPIC_KEYS.map((key) => {
      const pictogram = findTopicPictogram(key, symbolItems, TOPIC_EMOJI[key]);
      return {
        key,
        label: t(`topics.${key}`),
        topic: TOPIC_CANONICAL_NAME[key as CommonTopicKey],
        purpose: 'practice',
        practiced: practicedByKey.get(key) ?? false,
        imagePath: pictogram.imagePath,
        emoji: pictogram.emoji,
      };
    });

    // Attribution is only useful when the pool mixes several teachers, so a
    // lone teacher's topics stay uncluttered.
    const distinctCreators = new Set(
      savedTopics.map((topic) => topic.createdByUserId != null ? `id:${topic.createdByUserId}` : `name:${topic.createdBy}`),
    );
    const showSavedBy = distinctCreators.size > 1;

    const saved: PickerTopic[] = savedTopics.map((topic) => {
      const pictogram = findTopicPictogram(topic.topic, symbolItems, '💡');
      return {
        key: `saved-${topic.id}`,
        label: topic.topic,
        sublabel: topic.board,
        topic: topic.topic,
        purpose: topic.board,
        boardId: topic.boardId,
        practiced: recentByTopic.has(normalizeTopic(topic.topic)),
        imagePath: pictogram.imagePath,
        emoji: pictogram.emoji,
        ...(showSavedBy
          ? {
              savedBy: topic.createdBy,
              savedByUserId: topic.createdByUserId,
            }
          : {}),
      };
    });

    return [...common, ...saved];
  }, [savedTopics, symbolItems, t, topicPool]);

  const pickerRecent = useMemo<PickerRecentTopic[]>(() => {
    const poolKeys = new Set(pickerTopics.map((topic) => normalizeTopic(topic.topic)));
    return (topicPool?.recent ?? [])
      .filter((entry) => !poolKeys.has(normalizeTopic(entry.topic)))
      .map((entry) => ({ topic: entry.topic, purpose: entry.purpose }));
  }, [pickerTopics, topicPool]);

  return {
    pickerTopics,
    pickerRecent,
    fetchTopicPool,
    symbolItems,
    fetchSymbols,
    symbolLang,
    symbolLoading,
    symbolLanguage,
  };
}
