import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post, get } = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
}));

vi.mock('../src/lib/api', () => ({
  default: { post, get, put: vi.fn(), delete: vi.fn() },
  extractError: (error: unknown, fallback: string) => {
    const value = error as { response?: { data?: { detail?: string; error?: string; message?: string } }; message?: string };
    return value.response?.data?.detail || value.response?.data?.error || value.response?.data?.message || value.message || fallback;
  },
}));

import { useLearningStore, NEXT_QUESTION_REVEAL_DELAY_MS } from '../src/store/learningStore';
import { useAuthStore } from '../src/store/authStore';
import type { User } from '../src/types';

describe('learningStore adaptive question flow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    useLearningStore.setState({
      currentSession: null,
      currentQuestion: null,
      lastAnswer: null,
      revealedAnswer: null,
      progressStats: null,
      lastSessionSummary: null,
      isLoading: false,
      error: null,
      messages: [],
      providerInUse: undefined,
      providerHistory: [],
      sessionHistory: [],
      isLoadingHistory: false,
      showAdminReasoning: false,
      autoAskEnabled: true,
      difficultyOverride: 'adaptive',
    });
    useAuthStore.setState({ user: null });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('resetSession cancels pending auto-ask work and clears active learning state', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockResolvedValue({ data: { success: true, feedback_message: 'Answer received' } });

    await useLearningStore.getState().submitAnswer(7, 'Answer');
    useLearningStore.getState().resetSession();
    await vi.advanceTimersByTimeAsync(NEXT_QUESTION_REVEAL_DELAY_MS);

    const state = useLearningStore.getState();
    expect(state.currentSession).toBeNull();
    expect(state.messages).toEqual([]);
    expect(post.mock.calls.some(([url]) => url === '/learning/7/ask')).toBe(false);
  });

  it('askNextQuestion requests a question for the active session and stores it', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockResolvedValue({
      data: {
        success: true,
        question_text: 'What animal says miau?',
        choices: ['Cat', 'Dog', 'Cow'],
        correct_answer_index: 0,
      },
    });

    await useLearningStore.getState().askNextQuestion();

    expect(post).toHaveBeenCalledWith('/learning/7/ask', null, expect.anything());
    const state = useLearningStore.getState();
    expect(state.currentQuestion?.question_text).toBe('What animal says miau?');
    expect(state.currentQuestion?.choices).toEqual(['Cat', 'Dog', 'Cow']);
    expect(state.messages[state.messages.length - 1].content).toContain('What animal says miau?');
  });

  it('askNextQuestion does nothing when there is no active session', async () => {
    await useLearningStore.getState().askNextQuestion();
    expect(post).not.toHaveBeenCalled();
  });

  it('askNextQuestion applies a fixed difficulty override', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      difficultyOverride: 'advanced',
    });
    post.mockResolvedValue({
      data: {
        success: true,
        question_text: 'Advanced question',
        choices: ['A', 'B'],
        difficulty: 'advanced',
      },
    });

    await useLearningStore.getState().askNextQuestion();

    expect(post).toHaveBeenCalledWith('/learning/7/ask', null, {
      params: { difficulty: 'advanced' },
    });
  });

  it('askNextQuestion leaves difficulty undefined in adaptive mode', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      difficultyOverride: 'adaptive',
    });
    post.mockResolvedValue({
      data: { success: true, question_text: 'Adaptive question', choices: ['A', 'B'] },
    });

    await useLearningStore.getState().askNextQuestion();

    expect(post).toHaveBeenCalledWith('/learning/7/ask', null, {
      params: { difficulty: undefined },
    });
  });

  it('askNextQuestion is skipped while the question flow is paused (symbol view)', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    useLearningStore.getState().setAutoAskEnabled(false);

    await useLearningStore.getState().askNextQuestion();

    expect(post).not.toHaveBeenCalled();
    expect(useLearningStore.getState().currentQuestion).toBeNull();
  });

  it('askQuestion clears the previous question while a new one loads', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      currentQuestion: { success: true, question_text: 'Old question' },
    });
    post.mockResolvedValue({
      data: {
        success: true,
        question_text: 'New question',
        choices: ['A', 'B', 'C'],
        correct_answer_index: 2,
      },
    });

    await useLearningStore.getState().askQuestion(7);

    expect(useLearningStore.getState().currentQuestion?.question_text).toBe('New question');
  });

  it('submitAnswer appends messages and auto-requests the next question', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      currentQuestion: {
        success: true,
        question_text: 'What animal says miau?',
        choices: ['Cat', 'Dog', 'Cow'],
        correct_answer_index: 0,
      },
      messages: [{ role: 'assistant', content: 'What animal says miau?' }],
    });
    post
      .mockResolvedValueOnce({
        data: { success: true, feedback_message: '¡Muy bien!', is_correct: true },
      })
      .mockResolvedValueOnce({
        data: {
          success: true,
          question_text: 'Next question',
          choices: ['X', 'Y', 'Z'],
          correct_answer_index: 1,
        },
      });

    await useLearningStore.getState().submitAnswer(7, 'Cat');

    // The pending question is replaced by the auto-requested next question
    // (after the reveal delay so the correct answer stays visible).
    await vi.advanceTimersByTimeAsync(NEXT_QUESTION_REVEAL_DELAY_MS);
    expect(useLearningStore.getState().currentQuestion?.question_text).toBe('Next question');
    expect(useLearningStore.getState().messages.map((message) => message.content)).toEqual([
      'What animal says miau?',
      'Cat',
      '¡Muy bien!',
      'Next question',
    ]);
    expect(post).toHaveBeenCalledWith('/learning/7/answer', {
      answer: 'Cat',
      is_voice: false,
    });
    expect(post).toHaveBeenCalledWith('/learning/7/ask', null, expect.anything());
  });

  it('rapid double-tap on a choice submits only one answer', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      currentQuestion: {
        success: true,
        question_text: 'Which animal says miau?',
        choices: ['Cat', 'Dog', 'Cow'],
        correct_answer_index: 0,
      },
      messages: [],
    });
    post.mockResolvedValue({ data: { success: true, feedback_message: '¡Muy bien!' } });

    const store = useLearningStore.getState();
    // Fire both taps before the first request resolves: the isLoading guard
    // in submitAnswer must drop the second one.
    const first = store.submitAnswer(7, 'Cat');
    const second = store.submitAnswer(7, 'Cat');
    await Promise.all([first, second]);

    const answerCalls = post.mock.calls.filter((call) => call[0] === '/learning/7/answer');
    expect(answerCalls).toHaveLength(1);

    const state = useLearningStore.getState();
    expect(state.messages.filter((message) => message.content === 'Cat')).toHaveLength(1);
  });

  it('achievement refresh does not block answer completion', async () => {
    const user: User = {
      id: 42,
      username: 'student42',
      display_name: 'Student 42',
      user_type: 'student',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    useAuthStore.setState({ user });
    let resolveAchievement!: (value: unknown) => void;
    post.mockImplementation((url: string) => {
      if (url === '/learning/7/answer') {
        return Promise.resolve({ data: { success: true, feedback_message: 'Saved' } });
      }
      if (url === '/achievements/user/42/check') {
        return new Promise((resolve) => { resolveAchievement = resolve; });
      }
      return Promise.resolve({ data: { success: true } });
    });
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });

    await useLearningStore.getState().submitAnswer(7, 'Cat');

    expect(useLearningStore.getState().revealedAnswer).toEqual({ choice: 'Cat', isCorrect: null });
    expect(post).toHaveBeenCalledWith(
      '/achievements/user/42/check',
      undefined,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    resolveAchievement({ data: { success: true } });
  });

  it('auth logout aborts an in-flight achievement refresh', async () => {
    const user: User = {
      id: 42,
      username: 'student42',
      display_name: 'Student 42',
      user_type: 'student',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    useAuthStore.setState({ user });
    let resolveAnswer!: (value: unknown) => void;
    let achievementConfig: { signal?: AbortSignal } | undefined;
    post.mockImplementation((url: string, _body?: unknown, config?: { signal?: AbortSignal }) => {
      if (url === '/learning/7/answer') {
        return new Promise((resolve) => { resolveAnswer = resolve; });
      }
      if (url === '/achievements/user/42/check') {
        achievementConfig = config;
        return new Promise(() => {});
      }
      return Promise.resolve({ data: { success: true } });
    });
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });

    const answer = useLearningStore.getState().submitAnswer(7, 'Cat');
    resolveAnswer({ data: { success: true, feedback_message: 'Saved' } });
    await answer;
    await Promise.resolve();

    window.dispatchEvent(new Event('aac:auth-logout'));
    expect(achievementConfig?.signal?.aborted).toBe(true);
    expect(useLearningStore.getState().currentSession).toBeNull();
  });

  it('resetSession aborts an in-flight achievement refresh', async () => {
    const user: User = {
      id: 42,
      username: 'student42',
      display_name: 'Student 42',
      user_type: 'student',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    useAuthStore.setState({ user });
    let resolveAnswer!: (value: unknown) => void;
    let achievementConfig: { signal?: AbortSignal } | undefined;
    post.mockImplementation((url: string, _body?: unknown, config?: { signal?: AbortSignal }) => {
      if (url === '/learning/7/answer') {
        return new Promise((resolve) => { resolveAnswer = resolve; });
      }
      if (url === '/achievements/user/42/check') {
        achievementConfig = config;
        return new Promise(() => {});
      }
      return Promise.resolve({ data: { success: true } });
    });
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });

    const answer = useLearningStore.getState().submitAnswer(7, 'Cat');
    resolveAnswer({ data: { success: true, feedback_message: 'Saved' } });
    await answer;
    await Promise.resolve();
    expect(achievementConfig?.signal?.aborted).toBe(false);

    useLearningStore.getState().resetSession();
    expect(achievementConfig?.signal?.aborted).toBe(true);
  });

  it('submitVoiceAnswer also auto-requests the next question', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post
      .mockResolvedValueOnce({
        data: { success: true, transcription: 'Hola', feedback_message: 'Escuchado' },
      })
      .mockResolvedValueOnce({
        data: {
          success: true,
          question_text: 'Voice next question',
          choices: ['A', 'B', 'C'],
          correct_answer_index: 0,
        },
      });

    await useLearningStore.getState().submitVoiceAnswer(7, new Blob(['audio']));

    await vi.advanceTimersByTimeAsync(NEXT_QUESTION_REVEAL_DELAY_MS);
    expect(useLearningStore.getState().currentQuestion?.question_text).toBe(
      'Voice next question',
    );
    expect(post).toHaveBeenCalledWith(
      '/learning/7/answer/voice',
      expect.any(FormData),
      expect.anything(),
    );
  });

  it('submitAnswer keeps the question revealed with the correct/wrong highlight', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      currentQuestion: {
        success: true,
        question_text: 'What animal says miau?',
        choices: ['Cat', 'Dog', 'Cow'],
        correct_answer_index: 0,
      },
      messages: [{ role: 'assistant', content: 'What animal says miau?' }],
    });
    post
      .mockResolvedValueOnce({
        data: { success: true, feedback_message: 'Not quite', is_correct: false },
      })
      .mockResolvedValueOnce({
        data: {
          success: true,
          question_text: 'Next question',
          choices: ['X', 'Y', 'Z'],
          correct_answer_index: 1,
        },
      });

    await useLearningStore.getState().submitAnswer(7, 'Dog');

    const state = useLearningStore.getState();
    // The pending question stays visible so the highlight can be shown.
    expect(state.currentQuestion?.question_text).toBe('What animal says miau?');
    expect(state.revealedAnswer).toEqual({ choice: 'Dog', isCorrect: false });

    // After the reveal delay the next adaptive question replaces it.
    await vi.advanceTimersByTimeAsync(NEXT_QUESTION_REVEAL_DELAY_MS);
    expect(useLearningStore.getState().currentQuestion?.question_text).toBe('Next question');
    expect(useLearningStore.getState().revealedAnswer).toBeNull();
  });

  it('asking a new question clears the revealed answer state', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      revealedAnswer: { choice: 'Dog', isCorrect: false },
    });
    post.mockResolvedValue({
      data: {
        success: true,
        question_text: 'Fresh question',
        choices: ['A', 'B', 'C'],
        correct_answer_index: 0,
      },
    });

    await useLearningStore.getState().askQuestion(7);

    expect(useLearningStore.getState().revealedAnswer).toBeNull();
  });

  it('answer responses feed the in-session progress stats', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      currentQuestion: { success: true, question_text: 'Q', choices: ['A', 'B'], correct_answer_index: 0 },
    });
    post
      .mockResolvedValueOnce({
        data: {
          success: true,
          is_correct: true,
          comprehension_score: 0.5,
          questions_answered: 2,
          correct_answers: 1,
        },
      })
      .mockResolvedValueOnce({
        data: { success: true, question_text: 'Next', choices: ['A', 'B'], difficulty: 'advanced' },
      });

    await useLearningStore.getState().submitAnswer(7, 'A');

    await vi.advanceTimersByTimeAsync(NEXT_QUESTION_REVEAL_DELAY_MS);
    const state = useLearningStore.getState();
    expect(state.progressStats?.comprehensionScore).toBe(0.5);
    expect(state.progressStats?.questionsAnswered).toBe(2);
    expect(state.progressStats?.correctAnswers).toBe(1);
    expect(state.progressStats?.difficulty).toBe('advanced');
  });

  it('endSession captures the summary returned by the backend', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockResolvedValue({
      data: {
        success: true,
        session_id: 7,
        summary: 'Great work!',
        comprehension_score: 0.75,
        questions_answered: 4,
        correct_answers: 3,
      },
    });

    await useLearningStore.getState().endSession(7);

    const state = useLearningStore.getState();
    expect(state.currentSession).toBeNull();
    expect(state.lastSessionSummary?.summary).toBe('Great work!');
    expect(state.lastSessionSummary?.comprehension_score).toBe(0.75);

    useLearningStore.getState().clearSessionSummary();
    expect(useLearningStore.getState().lastSessionSummary).toBeNull();
  });

  it('a stale loadSession response cannot replace a newer session', async () => {
    let resolveFirst!: (value: unknown) => void;
    let resolveSecond!: (value: unknown) => void;
    get.mockImplementation((url: string) => {
      if (url === '/learning/1/progress') {
        return new Promise((resolve) => { resolveFirst = resolve; });
      }
      if (url === '/learning/2/progress') {
        return new Promise((resolve) => { resolveSecond = resolve; });
      }
      return Promise.resolve({ data: [] });
    });

    const first = useLearningStore.getState().loadSession(1);
    const second = useLearningStore.getState().loadSession(2);

    resolveSecond({ data: { id: 2, conversation_history: [] } });
    await second;
    resolveFirst({ data: { id: 1, conversation_history: [] } });
    await first;

    expect(useLearningStore.getState().currentSession?.session_id).toBe(2);
  });

  it('a stale answer response cannot overwrite a newly loaded session', async () => {
    let resolveAnswer!: (value: unknown) => void;
    post.mockImplementation((url: string) => {
      if (url === '/learning/7/answer') {
        return new Promise((resolve) => { resolveAnswer = resolve; });
      }
      return Promise.resolve({ data: { success: true } });
    });
    get.mockResolvedValue({ data: { id: 8, conversation_history: [] } });
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      messages: [{ role: 'assistant', content: 'Old question' }],
    });

    const answer = useLearningStore.getState().submitAnswer(7, 'Old answer');
    useLearningStore.setState({ currentSession: { session_id: 8, success: true }, isLoading: false });
    // Simulate the same invalidation used by a real session switch.
    await useLearningStore.getState().loadSession(8);
    resolveAnswer({ data: { success: true, feedback_message: 'Stale reply' } });
    await answer;

    expect(useLearningStore.getState().currentSession?.session_id).toBe(8);
    expect(useLearningStore.getState().messages.map((message) => message.content)).not.toContain('Stale reply');
  });

  it('a stale askQuestion response cannot replace a newer question request', async () => {
    let resolveFirst!: (value: unknown) => void;
    let resolveSecond!: (value: unknown) => void;
    post.mockImplementation((url: string) => {
      if (url !== '/learning/7/ask') return Promise.resolve({ data: { success: true } });
      return new Promise((resolve) => {
        if (!resolveFirst) resolveFirst = resolve;
        else resolveSecond = resolve;
      });
    });
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });

    const first = useLearningStore.getState().askQuestion(7);
    // A direct caller may intentionally replace an in-flight request; model
    // that explicit reset so the test exercises the per-request token guard
    // rather than the UI loading lock.
    useLearningStore.setState({ isLoading: false });
    const second = useLearningStore.getState().askQuestion(7);
    resolveSecond({ data: { success: true, question_text: 'Newest', choices: ['A'] } });
    await second;
    resolveFirst({ data: { success: true, question_text: 'Stale', choices: ['B'] } });
    await first;

    expect(useLearningStore.getState().currentQuestion?.question_text).toBe('Newest');
  });

  it('ignores a stale answer rejection after a newer answer succeeds', async () => {
    let rejectFirst!: (error: unknown) => void;
    let resolveSecond!: (value: unknown) => void;
    post.mockImplementation((url: string) => {
      if (url !== '/learning/7/answer') return Promise.resolve({ data: { success: true } });
      return new Promise((resolve, reject) => {
        if (!rejectFirst) rejectFirst = reject;
        else resolveSecond = resolve;
      });
    });
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });

    const first = useLearningStore.getState().submitAnswer(7, 'First');
    // Reset loading only to model a caller that allows a replacement operation.
    useLearningStore.setState({ isLoading: false });
    const second = useLearningStore.getState().submitAnswer(7, 'Second');
    resolveSecond({ data: { success: true, feedback_message: 'Newest reply' } });
    await second;
    rejectFirst(new Error('stale failure'));
    await first;

    expect(useLearningStore.getState().error).toBeNull();
    expect(useLearningStore.getState().messages.map((message) => message.content)).toContain('Newest reply');
  });

  it('keeps only the latest ten provider transitions', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      providerInUse: 'ollama',
      providerHistory: [],
    });
    post.mockImplementation(async () => {
      const current = useLearningStore.getState().providerInUse;
      return {
        data: {
          success: true,
          question_text: 'Question',
          choices: ['A', 'B'],
          provider_used: current === 'ollama' ? 'openrouter' : 'ollama',
        },
      };
    });

    for (let index = 0; index < 12; index += 1) {
      useLearningStore.setState({ isLoading: false });
      await useLearningStore.getState().askQuestion(7);
    }

    expect(useLearningStore.getState().providerHistory).toHaveLength(10);
  });

  it('askQuestion failure surfaces an error and keeps the store usable', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockResolvedValue({ data: { success: false, error: 'Invalid question format' } });

    await useLearningStore.getState().askNextQuestion();

    const state = useLearningStore.getState();
    expect(state.currentQuestion).toBeNull();
    expect(state.error).toBe('Invalid question format');
    expect(state.isLoading).toBe(false);
  });
});
