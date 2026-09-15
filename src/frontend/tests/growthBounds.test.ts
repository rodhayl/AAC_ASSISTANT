import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));

vi.mock('../src/lib/api', () => ({
  default: { post, get, put: vi.fn(), delete: vi.fn() },
  extractError: (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback,
}));

import { tts } from '../src/lib/tts';
import { MAX_CLIENT_MESSAGES, useLearningStore } from '../src/store/learningStore';
import { MAX_NOTIFICATION_ITEMS, useNotificationsStore } from '../src/store/notificationsStore';

describe('bounded client-side growth (G1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('bounds the per-key TTS debounce map across a long session', () => {
    const internals = tts as unknown as { lastSpokenAt: Map<string | number, number> };
    for (let i = 0; i < 2_000; i++) {
      tts.enqueue(`utterance-${i}`);
    }
    // One entry per distinct key was retained for the whole session before.
    expect(internals.lastSpokenAt.size).toBeLessThanOrEqual(200);
  });

  it('windows the learning transcript to the recent tail', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 1, success: true },
      messages: [],
      isSubmittingAnswer: false,
      isLoading: false,
    });
    post.mockResolvedValue({ data: { success: true, assistant_reply: 'ok' } });

    for (let i = 0; i < MAX_CLIENT_MESSAGES; i++) {
      await useLearningStore.getState().submitAnswer(1, `answer-${i}`);
    }

    const { messages } = useLearningStore.getState();
    expect(messages.length).toBeLessThanOrEqual(MAX_CLIENT_MESSAGES);
    // The window keeps the newest turns, not the oldest.
    expect(messages.at(-1)?.content).toBe('ok');
  });

  it('caps retained notifications and keeps the newest', () => {
    useNotificationsStore.setState({ items: [] });

    for (let i = 0; i < MAX_NOTIFICATION_ITEMS + 250; i++) {
      useNotificationsStore.getState().add({ title: `n-${i}`, message: 'body' });
    }

    const { items } = useNotificationsStore.getState();
    expect(items).toHaveLength(MAX_NOTIFICATION_ITEMS);
    expect(items[0].title).toBe(`n-${MAX_NOTIFICATION_ITEMS + 249}`);
  });
});
