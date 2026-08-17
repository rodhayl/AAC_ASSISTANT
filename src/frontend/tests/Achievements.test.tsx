import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Achievements } from '../src/pages/Achievements';

const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    username: 'teacher',
    display_name: 'Teacher',
    user_type: 'teacher' as const,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
}));

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    (selector ? selector(authState) : authState) as ReturnType<typeof useAuthStore>,
}));

vi.mock('../src/lib/api', () => ({
  default: api,
  extractError: (error: unknown, fallback: string) => {
    const value = error as { message?: string };
    return value.message || fallback;
  },
}));

const tFn = (key: string, defaultValue?: string | { defaultValue?: string }) => {
  if (typeof defaultValue === 'string') return defaultValue;
  return defaultValue?.defaultValue ?? key;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tFn }),
}));

const achievement = {
  id: 1,
  name: 'First Steps',
  description: 'Complete your first session',
  category: 'learning',
  points: 10,
  icon: '🏆',
  progress: 50,
  earned_at: null,
};

const earnedAchievement = {
  ...achievement,
  id: 2,
  name: 'Star Student',
  earned_at: '2026-01-02T00:00:00Z',
};

const managementAchievement = {
  id: 3,
  name: 'System Badge',
  description: 'Automatic badge',
  category: 'system',
  points: 20,
  icon: '⭐',
  created_by: null,
  is_manual: false,
  criteria_type: 'sessions_completed',
  criteria_value: 10,
  target_user_id: null,
};

const customAchievement = {
  ...managementAchievement,
  id: 4,
  name: 'Custom Badge',
  created_by: 1,
  is_manual: true,
  criteria_type: null,
  criteria_value: null,
};

const student = {
  id: 10,
  username: 'student10',
  display_name: 'Leo',
  user_type: 'student',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

describe('Achievements page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = {
      id: 1,
      username: 'teacher',
      display_name: 'Teacher',
      user_type: 'teacher' as const,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    api.get.mockImplementation((url: string) => {
      if (url === '/achievements/user/1') {
        return Promise.resolve({ data: [achievement, earnedAchievement] });
      }
      if (url === '/achievements/user/1/points') {
        return Promise.resolve({ data: 25 });
      }
      if (url === '/achievements/') {
        return Promise.resolve({ data: [managementAchievement, customAchievement] });
      }
      if (url === '/users/students') {
        return Promise.resolve({ data: [student] });
      }
      if (url === '/achievements/categories') {
        return Promise.resolve({ data: ['learning', 'system'] });
      }
      if (url === '/achievements/criteria-types') {
        return Promise.resolve({ data: ['sessions_completed'] });
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValue({ data: {} });
    api.put.mockResolvedValue({ data: {} });
    api.delete.mockResolvedValue({ data: {} });
  });

  it('renders the user achievement grid with locked and earned states', async () => {
    render(<Achievements />);

    expect(await screen.findByText('First Steps')).toBeInTheDocument();
    expect(screen.getByText('Star Student')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('re-checks achievements via the check button', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: 'check' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/achievements/user/1/check'),
    );
    expect(api.get).toHaveBeenCalledWith('/achievements/user/1');
  });

  it('shows an error when achievements fail to load', async () => {
    api.get.mockRejectedValue(new Error('server down'));
    render(<Achievements />);

    expect(await screen.findByText('server down')).toBeInTheDocument();
  });

  it('loads and renders the management table for teachers', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));

    expect(await screen.findByText('System Badge')).toBeInTheDocument();
    expect(screen.getByText('Custom Badge')).toBeInTheDocument();
    expect(screen.getAllByText('System').length).toBeGreaterThan(0);
    expect(screen.getByText('Custom')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/achievements/');
    expect(api.get).toHaveBeenCalledWith('/users/students');
  });

  it('creates an achievement from the create modal', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByRole('button', { name: /Create/ }));

    const dialog = await screen.findByRole('dialog');
    const nameInput = within(dialog).getAllByRole('textbox')[0];
    await user.type(nameInput, 'New Badge');
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/achievements/', {
        name: 'New Badge',
        description: '',
        category: 'custom',
        points: 10,
        icon: '🏆',
        target_user_id: null,
        criteria_type: null,
        criteria_value: null,
      }),
    );
  });

  it('edits a custom achievement', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByTitle('Edit'));

    const dialog = await screen.findByRole('dialog');
    const nameInput = within(dialog).getAllByRole('textbox')[0];
    await user.clear(nameInput);
    await user.type(nameInput, 'Renamed Badge');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/achievements/4', {
        name: 'Renamed Badge',
        description: 'Automatic badge',
        category: 'system',
        points: 20,
        icon: '⭐',
        criteria_type: null,
        criteria_value: null,
      }),
    );
  });

  it('deletes a custom achievement after confirmation', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByTitle('Delete'));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/achievements/4'));
    expect(window.confirm).toHaveBeenCalled();
  });

  it('awards an achievement to a selected student', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getAllByTitle('Award')[0]);

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByPlaceholderText(/Search student/), 'Leo');
    await user.click(within(dialog).getByText('Leo'));
    await user.click(within(dialog).getByRole('button', { name: 'Award' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/achievements/3/award', {
        user_id: 10,
      }),
    );
  });
});
