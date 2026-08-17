import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';

import { Dashboard } from '../src/pages/Dashboard';

const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    username: 'teacher',
    display_name: 'Ana',
    user_type: 'teacher' as const,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
}));

const boardState = vi.hoisted(() => ({
  boards: [] as unknown[],
  assignedBoards: [] as unknown[],
  fetchBoards: vi.fn(),
  fetchAssignedBoards: vi.fn(),
}));

const dashboardState = vi.hoisted(() => ({
  stats: null as {
    boardCount: number;
    learningStreak: number;
    achievementCount: number;
    totalPoints: number;
  } | null,
  recentActivity: [] as { type: string; description: string; timestamp: string }[],
  isLoading: false as boolean,
  fetchDashboardData: vi.fn(),
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    (selector ? selector(authState) : authState) as ReturnType<typeof useAuthStore>,
}));

vi.mock('../src/store/boardStore', () => ({
  useBoardStore: (selector?: (state: typeof boardState) => unknown) =>
    (selector ? selector(boardState) : boardState) as ReturnType<typeof useBoardStore>,
}));

vi.mock('../src/store/dashboardStore', () => ({
  useDashboardStore: (selector?: (state: typeof dashboardState) => unknown) =>
    (selector ? selector(dashboardState) : dashboardState) as ReturnType<typeof useDashboardStore>,
}));

vi.mock('../src/lib/format', () => ({
  formatDateTime: (value: string) => `formatted:${value}`,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const table: Record<string, string> = {
        'hero.welcome': `Welcome ${String((options as { name?: string } | undefined)?.name ?? '')}`,
        'hero.subtitle': 'Subtitle',
        'cards.myBoards': 'My boards',
        'cards.activeBoards': 'Active boards',
        'cards.manageBoards': 'Manage boards',
        'cards.assignedBoards': 'Assigned boards',
        'cards.assignedSubtitle': 'Assigned to you',
        'cards.viewBoards': 'View boards',
        'cards.learningStreak': 'Learning streak',
        'cards.days': `${String((options as { count?: number } | undefined)?.count ?? 0)} days`,
        'cards.keepWorking': 'Keep it up',
        'cards.startStreak': 'Start today',
        'cards.continueLearning': 'Continue learning',
        'cards.achievements': 'Achievements',
        'cards.badgesEarned': 'Badges earned',
        'cards.noBadges': 'No badges yet',
        'cards.viewAll': 'View all',
        'assigned.title': 'Assigned boards section',
        'assigned.subtitle': 'Your assignments',
        'assigned.noDescription': 'No description',
        'assigned.open': 'Open',
        'assigned.none': 'No assigned boards',
        'activity.recent': 'Recent activity',
        'activity.none': 'No activity yet',
      };
      return table[key] ?? key;
    },
  }),
}));

describe('Dashboard page', () => {
  const board = {
    id: 7,
    user_id: 1,
    name: 'Morning Routine',
    description: 'Daily steps',
    category: 'general',
    is_public: false,
    is_template: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    boardState.boards = [];
    boardState.assignedBoards = [];
    dashboardState.stats = { boardCount: 0, learningStreak: 3, achievementCount: 2, totalPoints: 40 };
    dashboardState.recentActivity = [];
    dashboardState.isLoading = false;
    authState.user = {
      id: 1,
      username: 'teacher',
      display_name: 'Ana',
      user_type: 'teacher' as const,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
  });

  const asStudent = () => {
    authState.user = { ...authState.user, username: 'student', display_name: 'Leo', user_type: 'student' };
  };

  function renderDashboard() {
    return render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
  }

  it('renders the hero, board counts, and fetches teacher data on mount', () => {
    renderDashboard();

    expect(screen.getByRole('heading', { name: 'Welcome Ana' })).toBeInTheDocument();
    expect(screen.getByText('My boards')).toBeInTheDocument();
    expect(screen.getByText('Learning streak')).toBeInTheDocument();
    expect(screen.getByText('Achievements')).toBeInTheDocument();
    expect(boardState.fetchBoards).toHaveBeenCalledWith(1);
    expect(boardState.fetchAssignedBoards).not.toHaveBeenCalled();
    expect(dashboardState.fetchDashboardData).toHaveBeenCalledWith(1);
    // Assigned-boards section is only rendered for students
    expect(screen.queryByText('Your assignments')).not.toBeInTheDocument();
  });

  it('fetches assigned boards and lists them for students', () => {
    asStudent();
    boardState.assignedBoards = [{ ...board, id: 42 }];
    renderDashboard();

    expect(boardState.fetchAssignedBoards).toHaveBeenCalledWith(1);
    expect(screen.getByText('Assigned boards section')).toBeInTheDocument();
    expect(screen.getByText('Morning Routine')).toBeInTheDocument();
    expect(screen.getByText('Daily steps')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^Open/ })).toHaveAttribute('href', '/boards/42');
  });

  it('shows loading placeholders while data is loading', () => {
    dashboardState.isLoading = true;
    renderDashboard();

    expect(screen.getAllByText('...').length).toBeGreaterThan(0);
  });

  it('renders recent activity and falls back to an empty state', () => {
    dashboardState.recentActivity = [
      {
        type: 'learning',
        description: 'Practiced "Colors"',
        timestamp: '2026-01-02T10:00:00Z',
      },
    ];
    renderDashboard();

    expect(screen.getByText('Recent activity')).toBeInTheDocument();
    expect(screen.getByText('Practiced "Colors"')).toBeInTheDocument();
    expect(screen.getByText('formatted:2026-01-02T10:00:00Z')).toBeInTheDocument();
  });

  it('shows the empty state when there is no recent activity', () => {
    renderDashboard();

    expect(screen.getByText('No activity yet')).toBeInTheDocument();
  });
});
