import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useTopicPickerPool } from '../src/hooks/useTopicPickerPool';
import api from '../src/lib/api';

const authState = vi.hoisted(() => ({
  user: { id: 5, username: 'student1', display_name: 'Alex', user_type: 'student' as const },
}));

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
    i18n: { language: 'es' },
  }),
}));

const apiMock = api as unknown as { get: ReturnType<typeof vi.fn> };

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
});
