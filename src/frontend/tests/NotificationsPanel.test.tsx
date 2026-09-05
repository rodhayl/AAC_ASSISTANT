import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotificationsPanel } from '../src/components/NotificationsPanel';

const storeState = vi.hoisted(() => ({
  items: [
    {
      id: 7,
      title: 'Board assigned',
      message: 'A new board is ready.',
      read: false,
      createdAt: 1,
      type: 'info',
    },
    {
      id: 8,
      title: 'Achievement Unlocked',
      message: 'First Steps (+10 pts)',
      read: true,
      createdAt: 2,
      type: 'achievement',
    },
    {
      id: 9,
      title: 'Achievement Unlocked',
      message: 'Custom Badge (+15 pts)',
      read: true,
      createdAt: 3,
      type: 'achievement',
    },
  ],
  markAsRead: vi.fn(),
  markAllAsRead: vi.fn(),
}));

vi.mock('../src/store/notificationsStore', () => ({
  useNotificationsStore: (selector?: (state: typeof storeState) => unknown) =>
    selector ? selector(storeState) : storeState,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) =>
      ({
        'notifications.title': 'Notifications',
        'notifications.markAll': 'Mark all as read',
        'notifications.close': 'Close',
        'notifications.achievementUnlocked': 'Logro desbloqueado',
        'systemAchievements.first_steps.name': 'Primeros Pasos',
        'systemAchievements.first_steps.description': 'Completa tu primera sesión',
      })[key] || defaultValue || key,
  }),
}));

describe('NotificationsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders notifications and routes read actions to the selected ids', () => {
    render(<NotificationsPanel onClose={vi.fn()} />);

    expect(screen.getByText('Board assigned')).toBeInTheDocument();
    expect(screen.getByText('A new board is ready.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Board assigned/i }));
    expect(storeState.markAsRead).toHaveBeenCalledWith(7);

    fireEvent.click(screen.getByRole('button', { name: 'Mark all as read' }));
    expect(storeState.markAllAsRead).toHaveBeenCalledWith();
  });

  it('localizes achievement notifications while leaving custom names intact', () => {
    render(<NotificationsPanel onClose={vi.fn()} />);

    // System achievement: both title and embedded name are localized.
    expect(screen.getAllByText('Logro desbloqueado')).toHaveLength(2);
    expect(screen.getByText('Primeros Pasos (+10 pts)')).toBeInTheDocument();

    // Custom achievement: localized title, stored name preserved.
    expect(screen.getByText('Custom Badge (+15 pts)')).toBeInTheDocument();

    // Non-achievement notifications are untouched.
    expect(screen.getByText('A new board is ready.')).toBeInTheDocument();
  });
});
