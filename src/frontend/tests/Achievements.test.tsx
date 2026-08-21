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

const otherTeacherAchievement = {
  ...managementAchievement,
  id: 5,
  name: 'Other Teacher Badge',
  created_by: 99,
  is_manual: true,
  criteria_type: null,
  criteria_value: null,
};

const zeroThresholdAchievement = {
  ...managementAchievement,
  id: 6,
  name: 'Zero Threshold Badge',
  created_by: 1,
  is_manual: false,
  criteria_type: 'sessions_completed',
  criteria_value: 0,
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
    await user.selectOptions(within(dialog).getAllByRole('combobox').at(-1)!, '10');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/achievements/4', {
        name: 'Renamed Badge',
        description: 'Automatic badge',
        category: 'system',
        points: 20,
        icon: '⭐',
        target_user_id: 10,
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

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/achievements/4'));
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

  it('skips network calls when there is no authenticated user', async () => {
    authState.user = null as unknown as (typeof authState)['user'];
    const user = userEvent.setup();
    render(<Achievements />);

    expect(screen.getByRole('button', { name: 'check' })).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'check' }));
    expect(api.post).not.toHaveBeenCalled();
  });

  it('creates an achievement with automatic criteria and a target student', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByRole('button', { name: /Create/ }));

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getAllByRole('textbox')[0], 'Auto Badge');
    await user.click(within(dialog).getByRole('button', { name: '⭐' }));
    await user.type(within(dialog).getAllByRole('textbox')[1], 'Automatic badge');
    await user.selectOptions(within(dialog).getAllByRole('combobox')[0], 'learning');
    await user.clear(within(dialog).getAllByRole('spinbutton')[0]);
    await user.type(within(dialog).getAllByRole('spinbutton')[0], '15');
    await user.click(within(dialog).getByLabelText('Automatic Criteria'));

    const combos = within(dialog).getAllByRole('combobox');
    await user.selectOptions(combos[1], 'sessions_completed');
    await user.clear(within(dialog).getAllByRole('spinbutton')[1]);
    await user.type(within(dialog).getAllByRole('spinbutton')[1], '5');
    await user.selectOptions(combos[2], '10');
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/achievements/', {
        name: 'Auto Badge',
        description: 'Automatic badge',
        category: 'learning',
        points: 15,
        icon: '⭐',
        target_user_id: 10,
        criteria_type: 'sessions_completed',
        criteria_value: 5,
      }),
    );
  });

  it('switches the award type back to manual in the editor', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByRole('button', { name: /Create/ }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText('Automatic Criteria'));
    expect(within(dialog).getAllByRole('combobox').length).toBe(3);

    await user.click(within(dialog).getByLabelText('Manual Award'));
    expect(within(dialog).getAllByRole('combobox').length).toBe(2);
  });

  it('closes the editor modal via the close button and the cancel button', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');

    await user.click(screen.getByRole('button', { name: /Create/ }));
    let dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText('Close'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    await user.click(screen.getByTitle('Edit'));
    dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('closes the award modal via the close and cancel buttons', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');

    await user.click(screen.getAllByTitle('Award')[0]);
    let dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText('Close'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    await user.click(screen.getAllByTitle('Award')[0]);
    dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows the achievement name and icon in the award modal', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getAllByTitle('Award')[0]);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('System Badge')).toBeInTheDocument();
    expect(within(dialog).getByText('⭐')).toBeInTheDocument();
  });

  it('keeps the achievement when the delete confirmation is dismissed', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByTitle('Delete'));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('shows an error when the re-check request fails', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue(new Error('check failed'));
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: 'check' }));

    expect(await screen.findByText('check failed')).toBeInTheDocument();
  });

  it('shows an error when creating an achievement fails', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue(new Error('create failed'));
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByRole('button', { name: /Create/ }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getAllByRole('textbox')[0], 'Badge');
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('create failed')).toBeInTheDocument();
  });

  it('shows an error when updating an achievement fails', async () => {
    const user = userEvent.setup();
    api.put.mockRejectedValue(new Error('update failed'));
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByTitle('Edit'));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('update failed')).toBeInTheDocument();
  });

  it('shows an error when deleting an achievement fails', async () => {
    const user = userEvent.setup();
    api.delete.mockRejectedValue(new Error('delete failed'));
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByTitle('Delete'));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText('delete failed')).toBeInTheDocument();
  });

  it('shows an error when awarding an achievement fails', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue(new Error('award failed'));
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getAllByTitle('Award')[0]);
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByPlaceholderText(/Search student/), 'Leo');
    await user.click(within(dialog).getByText('Leo'));
    await user.click(within(dialog).getByRole('button', { name: 'Award' }));

    expect(await screen.findByText('award failed')).toBeInTheDocument();
  });

  it('shows an error when part of the management data fails to load', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation((url: string) => {
      if (url === '/achievements/user/1') {
        return Promise.resolve({ data: [achievement] });
      }
      if (url === '/achievements/user/1/points') {
        return Promise.resolve({ data: 25 });
      }
      if (url === '/achievements/') {
        return Promise.resolve({ data: [managementAchievement] });
      }
      if (url === '/users/students') {
        return Promise.reject(new Error('students down'));
      }
      if (url === '/achievements/categories') {
        return Promise.resolve({ data: ['learning'] });
      }
      if (url === '/achievements/criteria-types') {
        return Promise.resolve({ data: ['sessions_completed'] });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));

    expect(
      await screen.findByText('Some management data could not be loaded. Please try again.'),
    ).toBeInTheDocument();
  });

  it('closes the editor modal with the Escape key', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByRole('button', { name: /Create/ }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('closes the delete confirmation with the Escape key', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByTitle('Delete'));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('disables create until a name is provided', async () => {
    const user = userEvent.setup();
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('System Badge');
    await user.click(screen.getByRole('button', { name: /Create/ }));

    const dialog = await screen.findByRole('dialog');
    const createButton = within(dialog).getByRole('button', { name: 'Create' });
    expect(createButton).toBeDisabled();

    await user.type(within(dialog).getAllByRole('textbox')[0], 'Named');
    expect(createButton).not.toBeDisabled();
  });

  it('preserves a zero criteria value when editing an automatic achievement', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation((url: string) => {
      if (url === '/achievements/user/1') {
        return Promise.resolve({ data: [achievement] });
      }
      if (url === '/achievements/user/1/points') {
        return Promise.resolve({ data: 25 });
      }
      if (url === '/achievements/') {
        return Promise.resolve({ data: [zeroThresholdAchievement] });
      }
      if (url === '/users/students') {
        return Promise.resolve({ data: [student] });
      }
      if (url === '/achievements/categories') {
        return Promise.resolve({ data: ['learning'] });
      }
      if (url === '/achievements/criteria-types') {
        return Promise.resolve({ data: ['sessions_completed'] });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('Zero Threshold Badge');
    await user.click(screen.getByTitle('Edit'));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/achievements/6', {
        name: 'Zero Threshold Badge',
        description: 'Automatic badge',
        category: 'system',
        points: 20,
        icon: '⭐',
        target_user_id: null,
        criteria_type: 'sessions_completed',
        criteria_value: 0,
      }),
    );
  });

  it('hides edit/delete actions for achievements owned by another teacher', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation((url: string) => {
      if (url === '/achievements/user/1') {
        return Promise.resolve({ data: [achievement] });
      }
      if (url === '/achievements/user/1/points') {
        return Promise.resolve({ data: 25 });
      }
      if (url === '/achievements/') {
        return Promise.resolve({ data: [otherTeacherAchievement] });
      }
      if (url === '/users/students') {
        return Promise.resolve({ data: [student] });
      }
      if (url === '/achievements/categories') {
        return Promise.resolve({ data: ['learning'] });
      }
      if (url === '/achievements/criteria-types') {
        return Promise.resolve({ data: ['sessions_completed'] });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Achievements />);
    await screen.findByText('First Steps');

    await user.click(screen.getByRole('button', { name: /Manage/ }));
    await screen.findByText('Other Teacher Badge');

    // Awarding any achievement stays available to every teacher/admin.
    expect(screen.getByTitle('Award')).toBeInTheDocument();
    // But editing/deleting a custom achievement owned by another teacher is
    // guaranteed to fail with 403, so the actions must not be offered.
    expect(screen.queryByTitle('Edit')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Delete')).not.toBeInTheDocument();
  });
});
