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
    t: (key: string) =>
      ({
        'notifications.title': 'Notifications',
        'notifications.markAll': 'Mark all as read',
        'notifications.close': 'Close',
      })[key] || key,
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
});
