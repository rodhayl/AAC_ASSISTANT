import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post, get, cancelAll } = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  cancelAll: vi.fn(),
}));

vi.mock('../src/lib/tts', () => ({
  tts: { cancelAll },
}));

vi.mock('../src/lib/api', () => ({
  default: { post, get, put: vi.fn(), delete: vi.fn() },
  extractError: (error: unknown, fallback: string) => {
    const value = error as { response?: { data?: { detail?: string; error?: string; message?: string } }; message?: string };
    return value.response?.data?.detail || value.response?.data?.error || value.response?.data?.message || value.message || fallback;
  },
}));

import { useLearningStore, NEXT_QUESTION_REVEAL_DELAY_MS, stripReasoning } from '../src/store/learningStore';
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
      isStartingSession: false,
      isAskingQuestion: false,
      isSubmittingAnswer: false,
      isEndingSession: false,
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

  it('startSession never sends the UI-only adaptive difficulty over the wire', async () => {
    useLearningStore.setState({ currentSession: null });
    post.mockResolvedValue({ data: { success: true, session_id: 11 } });

    await useLearningStore.getState().startSession(
      {
        topic: 'Space',
        purpose: 'practice',
        difficulty: 'adaptive',
        board_id: undefined,
        mode_key: 'guided',
      },
      1,
    );

    const call = post.mock.calls.find(([url]) => url === '/learning/start');
    expect(call).toBeDefined();
    const body = call[1] as { difficulty?: string };
    expect(body.difficulty).toBeUndefined();
    expect(JSON.stringify(body)).not.toContain('adaptive');
  });

  it('startSession passes concrete difficulty bands through', async () => {
    useLearningStore.setState({ currentSession: null });
    post.mockResolvedValue({ data: { success: true, session_id: 12 } });

    await useLearningStore.getState().startSession(
      { topic: 'Space', purpose: 'practice', difficulty: 'advanced', mode_key: 'guided' },
      1,
    );

    const call = post.mock.calls.find(([url]) => url === '/learning/start');
    const body = call[1] as { difficulty?: string };
    expect(body.difficulty).toBe('advanced');
  });

  it('resetSession cancels pending auto-ask work and clears active learning state', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockResolvedValue({
      data: { success: true, feedback_message: 'Answer received', is_correct: true },
    });

    await useLearningStore.getState().submitAnswer(7, 'Answer');
    useLearningStore.getState().resetSession();
    expect(cancelAll).toHaveBeenCalledTimes(1);
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

    expect(useLearningStore.getState().revealedAnswer).toEqual({
      choice: 'Cat',
      isCorrect: null,
      answerRevealed: false,
      wrongChoices: [],
    });
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
        data: { success: true, transcription: 'Hola', feedback_message: 'Escuchado', is_correct: true },
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

  it('a wrong answer keeps the same question open while hints are pending', async () => {
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
    post.mockResolvedValue({
      data: {
        success: true,
        feedback_message: 'Not quite, think of a pet',
        is_correct: false,
        answer_revealed: false,
      },
    });

    await useLearningStore.getState().submitAnswer(7, 'Dog');

    const state = useLearningStore.getState();
    // The pending question stays visible so the highlight can be shown.
    expect(state.currentQuestion?.question_text).toBe('What animal says miau?');
    expect(state.revealedAnswer).toEqual({
      choice: 'Dog',
      isCorrect: false,
      answerRevealed: false,
      wrongChoices: ['Dog'],
    });

    // No auto-advance: the student retries the same question after a hint.
    await vi.advanceTimersByTimeAsync(NEXT_QUESTION_REVEAL_DELAY_MS);
    expect(useLearningStore.getState().currentQuestion?.question_text).toBe('What animal says miau?');
    expect(post.mock.calls.some(([url]) => url === '/learning/7/ask')).toBe(false);
  });

  it('accumulates wrong picks so every failed choice stays disabled', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      currentQuestion: {
        success: true,
        question_text: 'What animal says miau?',
        choices: ['Cat', 'Dog', 'Cow'],
        correct_answer_index: 0,
      },
      messages: [],
    });
    post.mockResolvedValue({
      data: {
        success: true,
        feedback_message: 'Hint',
        is_correct: false,
        answer_revealed: false,
      },
    });

    await useLearningStore.getState().submitAnswer(7, 'Dog');
    // The retry is allowed because the store clears isLoading; submit the
    // second wrong pick.
    await useLearningStore.getState().submitAnswer(7, 'Cow');

    expect(useLearningStore.getState().revealedAnswer).toEqual({
      choice: 'Cow',
      isCorrect: false,
      answerRevealed: false,
      wrongChoices: ['Dog', 'Cow'],
    });

    // Repeating an already-failed pick does not duplicate it.
    await useLearningStore.getState().submitAnswer(7, 'Dog');
    expect(useLearningStore.getState().revealedAnswer?.wrongChoices).toEqual(['Dog', 'Cow']);
  });

  it('a wrong answer auto-advances once the backend revealed the answer', async () => {
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
        data: {
          success: true,
          feedback_message: "It was 'Cat'",
          is_correct: false,
          answer_revealed: true,
        },
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

  it('endSession clears the conversation while capturing the summary', async () => {
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      messages: [
        { role: 'assistant', content: 'Welcome' },
        { role: 'user', content: 'Answer' },
      ],
    });
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
    expect(state.messages).toEqual([]);
    expect(state.skipInitialSpeech).toBe(false);
    expect(post.mock.calls.some(([url]) => url === '/learning/start')).toBe(false);
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
    // that explicit reset so the test exercises the per-request epoch guard
    // rather than the in-flight duplicate-request guard.
    useLearningStore.setState({ isAskingQuestion: false, isLoading: false });
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
    // Reset the in-flight guard only to model a caller that force-clears it,
    // so the test exercises the stale-response epoch guard rather than the
    // concurrent duplicate-request guard.
    useLearningStore.setState({ isSubmittingAnswer: false, isLoading: false });
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

describe('learningStore resilience and history reconstruction', () => {
  it('stripReasoning removes think blocks and extracts the marked answer', () => {
    const withThinkBlock =
      'Let me think.\n<think>hidden chain of thought</think>\nThe answer is 4.';
    const result = stripReasoning(withThinkBlock);
    expect(result).not.toContain('hidden chain of thought');
    expect(result).toContain('answer is 4');
  });

  it('stripReasoning removes fenced reasoning blocks and answer markers', () => {
    const fenced = '```reasoning\nsome analysis\n```\nFinal answer: yes';
    expect(stripReasoning(fenced)).toBe('yes');
    expect(stripReasoning('<think>x</think>')).toBe('');
  });

  it('admins with reasoning enabled receive the full thinking trace', async () => {
    const admin: User = {
      id: 99,
      username: 'admin',
      display_name: 'Admin',
      user_type: 'admin',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    useAuthStore.setState({ user: admin });
    useLearningStore.setState({
      currentSession: { session_id: 7, success: true },
      showAdminReasoning: true,
    });
    post
      .mockResolvedValueOnce({
        data: { success: true, assistant_reply: 'Clean reply', full_thinking: 'model reasoning' },
      })
      .mockResolvedValueOnce({
        data: { success: true, question_text: 'Next', choices: ['A', 'B'] },
      });

    await useLearningStore.getState().submitAnswer(7, 'Cat');

    const contents = useLearningStore.getState().messages.map((message) => message.content);
    expect(contents[contents.length - 1]).toContain('Clean reply');
    expect(contents[contents.length - 1]).toContain('[debug] model reasoning');
  });

  it('startSession surfaces a non-Error rejection via extractError', async () => {
    post.mockRejectedValue({ response: { data: { detail: 'provider unavailable' } } });

    await expect(
      useLearningStore.getState().startSession({ topic: 'T', purpose: 'practice' }, 1),
    ).rejects.toThrow();
    expect(cancelAll).toHaveBeenCalledTimes(1);

    const state = useLearningStore.getState();
    expect(state.error).toBe('provider unavailable');
    expect(state.isLoading).toBe(false);
  });

  it('submitAnswer rejection sets an error when the request is current', async () => {
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockRejectedValue({ response: { data: { message: 'server down' } } });

    await useLearningStore.getState().submitAnswer(7, 'Cat');

    const state = useLearningStore.getState();
    expect(state.error).toBe('server down');
    expect(state.isLoading).toBe(false);
  });

  it('submitVoiceAnswer falls back to a placeholder when transcription is missing', async () => {
    // The store localizes its fallback via the real i18n instance; pin the
    // language so the expected text is deterministic. English is a lazy
    // chunk, so load it explicitly before switching.
    const { default: i18n, ensureLocale } = await import('../src/i18n/index');
    await ensureLocale('en');
    await i18n.changeLanguage('en');

    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockResolvedValue({ data: { success: true, feedback_message: 'Heard' } });

    await useLearningStore.getState().submitVoiceAnswer(7, new Blob(['audio']));

    const contents = useLearningStore.getState().messages.map((message) => message.content);
    expect(contents).toContain('[voice] Audio message');
    expect(useLearningStore.getState().revealedAnswer?.choice).toBe('[voice]');
  });

  it('endSession refreshes achievements and history for the active user', async () => {
    const student: User = {
      id: 42,
      username: 'student42',
      display_name: 'Student 42',
      user_type: 'student',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    useAuthStore.setState({ user: student });
    useLearningStore.setState({ currentSession: { session_id: 7, success: true } });
    post.mockImplementation((url: string) => {
      if (url === '/learning/7/end') {
        return Promise.resolve({ data: { success: true, summary: 'Great work!' } });
      }
      if (url === '/achievements/user/42/check') {
        return Promise.resolve({ data: { success: true } });
      }
      return Promise.resolve({ data: { success: true } });
    });
    get.mockResolvedValue({ data: { sessions: [] } });

    await useLearningStore.getState().endSession(7);

    expect(post).toHaveBeenCalledWith(
      '/achievements/user/42/check',
      undefined,
      expect.anything(),
    );
    // The history walk requests the first page with the maximum page size.
    expect(get).toHaveBeenCalledWith('/learning/history/42', { params: { limit: 1000 } });
  });

  it('fetchSessionHistory failure clears the loading flag', async () => {
    get.mockRejectedValue(new Error('boom'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await useLearningStore.getState().fetchSessionHistory(1);

    expect(useLearningStore.getState().isLoadingHistory).toBe(false);
    expect(consoleSpy).toHaveBeenCalled();
  });

  it('loadSession reconstructs question, text, symbol and feedback messages', async () => {
    get.mockResolvedValue({
      data: {
        id: 9,
        conversation_history: [
          { type: 'question', data: { question: 'What color is the sky?' } },
          { type: 'response', student_answer: 'Blue', feedback: 'Correct!', mode: 'text' },
          {
            type: 'response',
            student_answer: 'sky blue',
            symbols: [{ label: 'sky' }, { label: 'blue' }],
            mode: 'symbol',
          },
        ],
      },
    });

    await useLearningStore.getState().loadSession(9);

    expect(cancelAll).toHaveBeenCalled();
    const contents = useLearningStore.getState().messages.map((message) => message.content);
    expect(contents).toContain('What color is the sky?');
    expect(contents).toContain('Blue');
    expect(contents).toContain('Correct!');
    expect(contents.some((content) => content.startsWith('🧩 sky blue'))).toBe(true);
    expect(contents.some((content) => content.includes('[Symbols: sky, blue]'))).toBe(true);
    expect(useLearningStore.getState().currentSession?.session_id).toBe(9);
  });

  it('loadSession failure sets an error', async () => {
    get.mockRejectedValue({ message: 'not found' });
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await useLearningStore.getState().loadSession(9);

    const state = useLearningStore.getState();
    expect(state.error).toBe('not found');
    expect(state.isLoading).toBe(false);
    expect(consoleSpy).toHaveBeenCalled();
  });
});
