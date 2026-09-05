import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useTopicPickerPool } from '../src/hooks/useTopicPickerPool';
import api from '../src/lib/api';

const authState = vi.hoisted(() => ({
  user: { id: 5, username: 'student1', display_name: 'Alex', user_type: 'student' as const },
}));

const i18nState = vi.hoisted(() => ({ language: 'es' }));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

vi.mock('../src/store/learningStore', () => ({
  useLearningStore: () => null,
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: i18nState,
  }),
}));

const apiMock = api as unknown as { get: ReturnType<typeof vi.fn> };

type TopicPoolResponse = {
  common?: Array<{ key: string; practiced?: boolean }>;
  recent?: Array<{ topic: string; purpose?: string }>;
};

const savedTopics = [
  {
    id: 1,
    user_id: 2,
    board: 'El cielo',
    topic: 'Astronomía',
    created_by: 'Ms. Johnson',
    created_at: '2026-01-05T00:00:00Z',
  },
  {
    id: 2,
    user_id: 3,
    board: 'Recetas',
    topic: 'Cocina',
    created_by: 'Mr. García',
    created_at: '2026-01-06T00:00:00Z',
  },
];

describe('useTopicPickerPool savedBy attribution', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { id: 5, username: 'student1', display_name: 'Alex', user_type: 'student' };
    i18nState.language = 'es';
    // Topic pool: all nine common topics fresh, no recent sessions.
    apiMock.get.mockImplementation(async (url: string) => {
      if (url.includes('/learning/topics/saved')) return { data: savedTopics };
      if (url.includes('/learning/topics')) {
        return {
          data: {
            common: [],
            recent: [],
          },
        };
      }
      if (url.includes('/boards/symbols')) return { data: [] };
      return { data: [] };
    });
  });

  it('labels saved cards when topics come from multiple teachers', async () => {
    const { result } = renderHook(() => useTopicPickerPool());
    await waitFor(() => {
      const saved = result.current.pickerTopics.filter((t) => t.key.startsWith('saved-'));
      expect(saved).toHaveLength(2);
      expect(saved[0].savedBy).toBeDefined();
      expect(saved[1].savedBy).toBeDefined();
    });
  });

  it('omits the label when only one teacher saved topics', async () => {
    apiMock.get.mockImplementation(async (url: string) => {
      if (url.includes('/learning/topics/saved')) return { data: [savedTopics[0]] };
      if (url.includes('/learning/topics')) return { data: { common: [], recent: [] } };
      if (url.includes('/boards/symbols')) return { data: [] };
      return { data: [] };
    });

    const { result } = renderHook(() => useTopicPickerPool());
    await waitFor(() => {
      expect(result.current.pickerTopics.some((t) => t.key.startsWith('saved-'))).toBe(true);
    });
    const saved = result.current.pickerTopics.filter((t) => t.key.startsWith('saved-'));
    expect(saved[0].savedBy).toBeUndefined();
  });

  it('ignores a topic-pool response from a previous auth context', async () => {
    let resolveFirst: ((value: { data: TopicPoolResponse }) => void) | undefined;
    let resolveSecond: ((value: { data: TopicPoolResponse }) => void) | undefined;

    apiMock.get.mockImplementation((url: string, config?: { params?: { user_id?: number } }) => {
      if (url === '/learning/topics') {
        return new Promise<{ data: TopicPoolResponse }>((resolve) => {
          if (config?.params?.user_id === 5) resolveFirst = resolve;
          else resolveSecond = resolve;
        });
      }
      if (url.includes('/learning/topics/saved')) return Promise.resolve({ data: [] });
      if (url.includes('/boards/symbols')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    const { result, rerender } = renderHook(() => useTopicPickerPool());
    await waitFor(() => expect(resolveFirst).toBeDefined());

    authState.user = { id: 6, username: 'student2', display_name: 'Sam', user_type: 'student' };
    rerender();
    await waitFor(() => expect(resolveSecond).toBeDefined());

    await act(async () => {
      resolveFirst?.({ data: { common: [], recent: [{ topic: 'User 5 private topic' }] } });
      await Promise.resolve();
    });
    expect(result.current.pickerRecent).not.toContainEqual({ topic: 'User 5 private topic', purpose: undefined });

    await act(async () => {
      resolveSecond?.({ data: { common: [], recent: [{ topic: 'User 6 topic' }] } });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.pickerRecent).toContainEqual({ topic: 'User 6 topic', purpose: undefined });
    });
  });

  it('ignores a symbol response from a previous locale', async () => {
    let resolveSpanish: ((value: { data: Array<Record<string, unknown>> }) => void) | undefined;
    let resolveEnglish: ((value: { data: Array<Record<string, unknown>> }) => void) | undefined;

    apiMock.get.mockImplementation((url: string, config?: { params?: { language?: string } }) => {
      if (url === '/boards/symbols') {
        return new Promise<{ data: Array<Record<string, unknown>> }>((resolve) => {
          if (config?.params?.language === 'es') resolveSpanish = resolve;
          else resolveEnglish = resolve;
        });
      }
      if (url.includes('/learning/topics/saved')) return Promise.resolve({ data: [] });
      if (url.includes('/learning/topics')) return Promise.resolve({ data: { common: [], recent: [] } });
      return Promise.resolve({ data: [] });
    });

    const { result, rerender } = renderHook(() => useTopicPickerPool());
    await waitFor(() => expect(resolveSpanish).toBeDefined());

    i18nState.language = 'en';
    rerender();
    await waitFor(() => expect(resolveEnglish).toBeDefined());

    await act(async () => {
      resolveSpanish?.({ data: [{ id: 1, label: 'Hola', image_path: '/hola.png' }] });
      await Promise.resolve();
    });
    expect(result.current.symbolItems).toEqual([]);
    expect(result.current.symbolLang).toBe('');

    await act(async () => {
      resolveEnglish?.({ data: [{ id: 2, label: 'Hello', image_path: '/hello.png' }] });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.symbolItems).toEqual([
        expect.objectContaining({ id: 2, label: 'Hello', image_path: '/hello.png' }),
      ]);
      expect(result.current.symbolLang).toBe('en');
      expect(result.current.symbolLoading).toBe(false);
    });
  });
});
