import { describe, it, expect, beforeEach } from 'vitest';
import { addTopic, loadTopicsForUser, removeTopic } from './learningTopics';
import type { SavedTopic } from './learningTopics';

const userId = 123;

describe('learningTopics storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('saves and loads topics per user', () => {
    const topic: SavedTopic = { id: 1, board: 'Board A', topic: 'Greetings', createdBy: 'Teacher' };
    addTopic(userId, topic);
    const loaded = loadTopicsForUser(userId);
    expect(loaded).toHaveLength(1);
    expect(loaded[0].topic).toBe('Greetings');
  });

  it('does not leak topics across users', () => {
    addTopic(userId, { id: 1, board: 'Board A', topic: 'Greetings', createdBy: 'Teacher' });
    addTopic(999, { id: 2, board: 'Board B', topic: 'Colors', createdBy: 'Teacher' });
    expect(loadTopicsForUser(userId)).toHaveLength(1);
    expect(loadTopicsForUser(999)).toHaveLength(1);
    expect(loadTopicsForUser(userId)[0].topic).toBe('Greetings');
  });

  it('removes a topic', () => {
    addTopic(userId, { id: 1, board: 'Board A', topic: 'Greetings', createdBy: 'Teacher' });
    const after = removeTopic(userId, 1);
    expect(after).toHaveLength(0);
    expect(loadTopicsForUser(userId)).toHaveLength(0);
  });
});
