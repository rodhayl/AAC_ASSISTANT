import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Dashboard } from '../src/pages/Dashboard';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (key === 'hero.welcome') return `Welcome, ${String(options?.name ?? '')}`.trim();
      if (key === 'cards.days') return `${options?.count} days`;
      const map: Record<string, string> = {
        'cards.myBoards': 'My boards',
        'cards.assignedBoards': 'Assigned boards',
        'assigned.title': 'Assigned to me',
        'assigned.open': 'Open',
        'assigned.none': 'No assigned boards',
        'activity.recent': 'Recent activity',
        'activity.none': 'No recent activity',
      };
      return map[key] || key;
    },
  }),
}));

vi.mock('react-router', () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock('../src/lib/format', () => ({
  formatDateTime: () => '2026-08-16 10:00',
}));

const authState = vi.hoisted(() => ({ user: null as unknown }));
const boardState = vi.hoisted(() => ({
  boards: [] as { id: number; name: string; description?: string }[],
  assignedBoards: [] as { id: number; name: string; description?: string }[],
  fetchBoards: vi.fn(),
  fetchAssignedBoards: vi.fn(),
}));
const dashboardState = vi.hoisted(() => ({
  stats: { learningStreak: 3, achievementCount: 2 },
  recentActivity: [{ description: 'Completed a session', timestamp: '2026-08-16' }],
  fetchDashboardData: vi.fn(),
  isLoading: false,
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (s: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));
vi.mock('../src/store/boardStore', () => ({
  useBoardStore: (selector?: (s: typeof boardState) => unknown) =>
    selector ? selector(boardState) : boardState,
}));
vi.mock('../src/store/dashboardStore', () => ({
  useDashboardStore: (selector?: (s: typeof dashboardState) => unknown) =>
    selector ? selector(dashboardState) : dashboardState,
}));

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches data for the signed-in user and renders student cards', () => {
    authState.user = { id: 9, display_name: 'Sam', user_type: 'student' };
    boardState.boards = [{ id: 1, name: 'My board' }];
    boardState.assignedBoards = [{ id: 2, name: 'Teacher board' }];

    render(<Dashboard />);

    expect(boardState.fetchBoards).toHaveBeenCalledWith(9);
    expect(boardState.fetchAssignedBoards).toHaveBeenCalledWith(9);
    expect(dashboardState.fetchDashboardData).toHaveBeenCalledWith(9);

    expect(screen.getByText('Welcome, Sam')).toBeInTheDocument();
    expect(screen.getByText('Assigned boards')).toBeInTheDocument();
    expect(screen.getByText('Teacher board')).toBeInTheDocument();
    expect(screen.getByText('3 days')).toBeInTheDocument();
  });

  it('does not render the assigned-boards section for admins', () => {
    authState.user = { id: 1, display_name: 'Alex', user_type: 'admin' };
    boardState.assignedBoards = [];

    render(<Dashboard />);

    expect(screen.queryByText('Assigned boards')).not.toBeInTheDocument();
    expect(boardState.fetchAssignedBoards).not.toHaveBeenCalled();
  });
});
