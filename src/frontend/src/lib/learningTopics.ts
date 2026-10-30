export type SavedTopic = { id: number; board: string; topic: string; createdBy: string };

const keyForUser = (userId: number) => `learning-topics-${userId}`;

export function loadTopicsForUser(userId: number): SavedTopic[] {
  try {
    const raw = localStorage.getItem(keyForUser(userId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter(
        (t) => typeof t?.id === 'number' && typeof t?.topic === 'string'
      ) as SavedTopic[];
    }
  } catch {
    /* ignore */
  }
  return [];
}

export function saveTopicsForUser(userId: number, topics: SavedTopic[]) {
  try {
    localStorage.setItem(keyForUser(userId), JSON.stringify(topics));
  } catch {
    /* ignore */
  }
}

export function addTopic(userId: number, topic: SavedTopic): SavedTopic[] {
  const topics = loadTopicsForUser(userId);
  const next = [...topics, topic];
  saveTopicsForUser(userId, next);
  return next;
}

export function removeTopic(userId: number, topicId: number): SavedTopic[] {
  const next = loadTopicsForUser(userId).filter((t) => t.id !== topicId);
  saveTopicsForUser(userId, next);
  return next;
}
