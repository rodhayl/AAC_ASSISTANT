import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
  },
  extractError: (_error: unknown, fallback: string) => fallback,
}));

import api from '../src/lib/api';
import { useDashboardStore } from '../src/store/dashboardStore';

const today = new Date();

describe('dashboard store learning streak', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDashboardStore.setState({
      stats: null,
      recentActivity: [],
      isLoading: false,
      error: null,
    });
    vi.mocked(api.get).mockImplementation((url) => {
      if (url.includes('/achievements/user/1/points')) {
        return Promise.resolve({ data: 25 }) as never;
      }
      if (url.includes('/achievements/user/1')) {
        return Promise.resolve({ data: [] }) as never;
      }
      if (url === '/learning/history/1') {
        return Promise.resolve({ data: { sessions: [] } }) as never;
      }
      throw new Error(`Unexpected URL: ${url}`);
    });
  });

  it('requests a bounded history window and counts consecutive active days', async () => {
    const sessions = Array.from({ length: 6 }, (_, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - index);
      return {
        id: index + 1,
        topic: `Topic ${index + 1}`,
        created_at: date.toISOString(),
      };
    });

    vi.mocked(api.get).mockImplementation((url, config) => {
      if (url.includes('/achievements/user/1/points')) {
        return Promise.resolve({ data: 25 }) as never;
      }
      if (url.includes('/achievements/user/1')) {
        return Promise.resolve({ data: [] }) as never;
      }
      if (url === '/learning/history/1') {
        const limit = (config?.params as { limit?: number } | undefined)?.limit ?? 0;
        return Promise.resolve({ data: { sessions: sessions.slice(0, limit) } }) as never;
      }
      throw new Error(`Unexpected URL: ${url}`);
    });

    await useDashboardStore.getState().fetchDashboardData(1);

    expect(api.get).toHaveBeenCalledWith('/learning/history/1', {
      params: { limit: 100 },
    });
    expect(useDashboardStore.getState().stats?.learningStreak).toBe(6);
    expect(useDashboardStore.getState().recentActivity).toHaveLength(6);
  });
});
