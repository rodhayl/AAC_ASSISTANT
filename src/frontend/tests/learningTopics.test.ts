import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  addTopic,
  loadTopicsForUser,
  migrateLocalTopicsToBackend,
  removeTopic,
} from '../src/lib/learningTopics';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const apiMock = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

const userId = 123;

describe('learningTopics backend store', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('loads topics from the backend', async () => {
    apiMock.get.mockResolvedValue({
      data: [
        { id: 1, board: 'Board A', board_id: 7, topic: 'Greetings', created_by: 'Teacher' },
        { id: 2, board: 'Board B', topic: 'Colors', created_by: 'Teacher' },
      ],
    });

    const loaded = await loadTopicsForUser(userId);
    expect(loaded).toEqual([
      { id: 1, board: 'Board A', boardId: 7, topic: 'Greetings', createdBy: 'Teacher' },
      { id: 2, board: 'Board B', topic: 'Colors', createdBy: 'Teacher' },
    ]);
    expect(apiMock.get).toHaveBeenCalledWith('/learning/topics/saved');
  });

  it('returns an empty list when the backend has no topics', async () => {
    apiMock.get.mockResolvedValue({ data: [] });
    expect(await loadTopicsForUser(userId)).toEqual([]);
  });

  it('adds a topic through the backend', async () => {
    apiMock.post.mockResolvedValue({
      data: { id: 10, board: 'Board A', topic: 'Greetings', created_by: 'Teacher' },
    });

    const created = await addTopic(userId, { board: 'Board A', topic: 'Greetings' });
    expect(created).toEqual({ id: 10, board: 'Board A', topic: 'Greetings', createdBy: 'Teacher' });
    expect(apiMock.post).toHaveBeenCalledWith('/learning/topics/saved', {
      board: 'Board A',
      board_id: null,
      topic: 'Greetings',
    });
  });

  it('removes a topic through the backend', async () => {
    apiMock.delete.mockResolvedValue({});
    await removeTopic(userId, 42);
    expect(apiMock.delete).toHaveBeenCalledWith('/learning/topics/saved/42');
  });

  it('migrates legacy localStorage topics into the backend once', async () => {
    localStorage.setItem(
      `learning-topics-${userId}`,
      JSON.stringify([
        { id: 1, board: 'Board A', topic: 'Greetings', createdBy: 'Teacher' },
        { id: 2, board: 'Board B', boardId: 3, topic: 'Colors', createdBy: 'Teacher' },
      ]),
    );
    apiMock.post.mockResolvedValue({});

    await migrateLocalTopicsToBackend(userId);

    expect(apiMock.post).toHaveBeenCalledTimes(2);
    expect(apiMock.post).toHaveBeenNthCalledWith(1, '/learning/topics/saved', {
      board: 'Board A',
      board_id: null,
      topic: 'Greetings',
    });
    expect(apiMock.post).toHaveBeenNthCalledWith(2, '/learning/topics/saved', {
      board: 'Board B',
      board_id: 3,
      topic: 'Colors',
    });
    expect(localStorage.getItem(`learning-topics-${userId}`)).toBeNull();
  });

  it('migrates once when called concurrently (sidebar + pool mount together)', async () => {
    localStorage.setItem(
      `learning-topics-${userId}`,
      JSON.stringify([{ id: 1, board: 'Board A', topic: 'Greetings', createdBy: 'Teacher' }]),
    );
    apiMock.post.mockResolvedValue({});

    // Two surfaces (BoardsAndTopicsSidebar + useTopicPickerPool) both run the
    // migration on mount; the second must wait and find nothing left.
    await Promise.all([
      migrateLocalTopicsToBackend(userId),
      migrateLocalTopicsToBackend(userId),
    ]);

    expect(apiMock.post).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(`learning-topics-${userId}`)).toBeNull();
  });

  it('keeps local topics when the migration upload fails', async () => {
    localStorage.setItem(
      `learning-topics-${userId}`,
      JSON.stringify([{ id: 1, board: 'Board A', topic: 'Greetings', createdBy: 'Teacher' }]),
    );
    apiMock.post.mockRejectedValue(new Error('offline'));

    await migrateLocalTopicsToBackend(userId);
    expect(localStorage.getItem(`learning-topics-${userId}`)).not.toBeNull();
  });

  it('skips migration when there is no legacy data', async () => {
    await migrateLocalTopicsToBackend(userId);
    expect(apiMock.post).not.toHaveBeenCalled();
  });
});
