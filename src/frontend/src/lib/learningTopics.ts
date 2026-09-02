import api from './api';

export type SavedTopic = {
  id: number;
  board: string;
  boardId?: number;
  topic: string;
  createdBy: string;
};

/**
 * Saved topics now live in the backend (`/learning/topics/saved`) so a
 * student sees their teacher's topics on any device. The localStorage
 * helpers below exist only for the one-time migration of data that predates
 * server-side storage; they are removed after a successful upload.
 */

const keyForUser = (userId: number) => `learning-topics-${userId}`;

function loadLocalTopics(userId: number): SavedTopic[] {
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

// The Learning page mounts both the sidebar and the topic-picker pool, and
// each triggers the migration on mount. Serialize them through a single
// in-flight promise so the second caller waits for the first to finish (and
// find the localStorage key already gone) instead of double-posting.
const migrationsInFlight = new Map<number, Promise<void>>();

/**
 * One-time migration: push topics still sitting in legacy localStorage into
 * the backend, then clear the local copy. Only call for users who can
 * create topics (teacher/admin) — the endpoint rejects students.
 */
export function migrateLocalTopicsToBackend(userId: number): Promise<void> {
  const existing = migrationsInFlight.get(userId);
  if (existing) return existing;

  const migration = doMigrateLocalTopics(userId).finally(() => {
    if (migrationsInFlight.get(userId) === migration) {
      migrationsInFlight.delete(userId);
    }
  });
  migrationsInFlight.set(userId, migration);
  return migration;
}

async function doMigrateLocalTopics(userId: number): Promise<void> {
  const local = loadLocalTopics(userId);
  if (local.length === 0) return;
  try {
    for (const topic of local) {
      await api.post('/learning/topics/saved', {
        board: topic.board,
        board_id: topic.boardId ?? null,
        topic: topic.topic,
      });
    }
    localStorage.removeItem(keyForUser(userId));
  } catch {
    // Keep the local copy so the migration retries on the next load.
  }
}

function mapFromApi(raw: {
  id: number;
  board: string;
  board_id?: number | null;
  topic: string;
  created_by: string;
}): SavedTopic {
  return {
    id: raw.id,
    board: raw.board,
    ...(raw.board_id != null ? { boardId: raw.board_id } : {}),
    topic: raw.topic,
    createdBy: raw.created_by,
  };
}

export async function loadTopicsForUser(
  userId: number,
  migrate = false
): Promise<SavedTopic[]> {
  if (migrate) {
    await migrateLocalTopicsToBackend(userId);
  }
  const { data } = await api.get('/learning/topics/saved');
  return Array.isArray(data) ? data.map(mapFromApi) : [];
}

export async function addTopic(
  _userId: number,
  topic: Omit<SavedTopic, 'id' | 'createdBy'>
): Promise<SavedTopic> {
  const { data } = await api.post('/learning/topics/saved', {
    board: topic.board,
    board_id: topic.boardId ?? null,
    topic: topic.topic,
  });
  return mapFromApi(data);
}

export async function removeTopic(_userId: number, topicId: number): Promise<void> {
  await api.delete(`/learning/topics/saved/${topicId}`);
}
