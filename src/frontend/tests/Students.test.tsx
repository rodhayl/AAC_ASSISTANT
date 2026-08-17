import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Students } from '../src/pages/Students';

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
  patch: vi.fn(),
}));

const tFn = (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key;

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    (selector ? selector(authState) : authState) as ReturnType<typeof useAuthStore>,
}));

vi.mock('../src/lib/api', () => ({
  default: api,
  extractError: (_error: unknown, fallback: string) => fallback,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tFn }),
}));

const studentSummary = {
  id: 10,
  username: 'student10',
  display_name: 'Leo',
  user_type: 'student',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  assigned_boards: [{ id: 42, name: 'Morning Routine' }],
};

const board = {
  id: 42,
  user_id: 1,
  name: 'Morning Routine',
  description: 'Daily steps',
  category: 'general',
  is_public: false,
  is_template: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('Students page', () => {
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
      if (url === '/auth/users/student-summaries') {
        return Promise.resolve({ data: [studentSummary] });
      }
      if (url === '/boards/') {
        return Promise.resolve({ data: [board] });
      }
      if (url === '/auth/users/10/preferences') {
        return Promise.resolve({ data: { voice_mode_enabled: true } });
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValue({ data: {} });
    api.put.mockResolvedValue({ data: {} });
    api.delete.mockResolvedValue({ data: {} });
  });

  const asAdmin = () => {
    authState.user = { ...authState.user, user_type: 'admin' as const, username: 'admin' };
  };

  it('renders the student list with assigned boards and an empty placeholder', async () => {
    api.get.mockImplementation((url: string) => {
      if (url === '/auth/users/student-summaries') {
        return Promise.resolve({ data: [{ ...studentSummary, assigned_boards: [] }] });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Students />);

    expect(await screen.findByText('Leo')).toBeInTheDocument();
    expect(screen.getByText('student10')).toBeInTheDocument();
    expect(screen.getByText('noneAssigned')).toBeInTheDocument();
  });

  it('shows the assigned board badge and unassigns it', async () => {
    const user = userEvent.setup();
    render(<Students />);

    expect(await screen.findByText('Morning Routine')).toBeInTheDocument();
    await user.click(screen.getByLabelText('actions.unassignAria'));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/boards/42/assign/10'),
    );
    await waitFor(() =>
      expect(screen.getByText('noneAssigned')).toBeInTheDocument(),
    );
  });

  it('creates a student through the teacher route and refreshes the list', async () => {
    const user = userEvent.setup();
    render(<Students />);
    await screen.findByText('Leo');

    await user.click(screen.getByRole('button', { name: /create/i }));
    await user.type(screen.getByLabelText('labels.username'), 'new_student');
    await user.type(screen.getByLabelText('labels.displayName'), 'New Student');
    await user.type(screen.getByLabelText('labels.password'), 'StudentPass123');
    await user.click(screen.getByText('createBtn'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/users/students', {
        username: 'new_student',
        password: 'StudentPass123',
        display_name: 'New Student',
        email: undefined,
        user_type: 'student',
      }),
    );
    expect(api.get).toHaveBeenCalledWith('/auth/users/student-summaries', {
      params: { limit: 100 },
    });
  });

  it('rejects a password mismatch when an admin creates a student', async () => {
    const user = userEvent.setup();
    asAdmin();
    render(<Students />);
    await screen.findByText('Leo');

    await user.click(screen.getByRole('button', { name: /create/i }));
    await user.type(screen.getByLabelText('labels.username'), 'new_student');
    await user.type(screen.getByLabelText('labels.displayName'), 'New Student');
    await user.type(screen.getByLabelText('labels.password'), 'StudentPass123');
    await user.type(screen.getByLabelText('Confirm Password'), 'Different123');
    await user.click(screen.getByText('createBtn'));

    await waitFor(() =>
      expect(screen.getAllByText('Passwords do not match').length).toBeGreaterThan(0),
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it('deletes a student after confirming in the dialog', async () => {
    const user = userEvent.setup();
    asAdmin();
    render(<Students />);
    await screen.findByText('Leo');

    await user.click(screen.getByLabelText('actions.deleteAria'));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByText('delete'));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/auth/users/10'));
    expect(screen.queryByText('Leo')).not.toBeInTheDocument();
  });

  it('marks already-assigned boards as disabled in the assign modal', async () => {
    const user = userEvent.setup();
    render(<Students />);
    await screen.findByText('Leo');

    await user.click(screen.getByLabelText('actions.assignAria'));

    const dialog = await screen.findByRole('dialog');
    const boardButton = within(dialog).getByRole('button', { name: /Morning Routine/ });
    expect(boardButton).toBeDisabled();
    expect(within(dialog).getByText('alreadyAssigned')).toBeInTheDocument();
  });

  it('opens the preferences modal, toggles voice mode and saves', async () => {
    const user = userEvent.setup();
    render(<Students />);
    await screen.findByText('Leo');

    await user.click(screen.getByTitle('Preferences'));
    expect(await screen.findByText(/Preferences for/)).toBeInTheDocument();

    const toggle = screen.getByLabelText('Voice Mode') as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    await user.click(toggle);

    await user.click(screen.getByText('save'));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/auth/users/10/preferences', {
        voice_mode_enabled: false,
      }),
    );
  });

  it('resets a student password from the modal', async () => {
    const user = userEvent.setup();
    render(<Students />);
    await screen.findByText('Leo');

    await user.click(screen.getByLabelText(/Reset password for student10/));
    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByLabelText('New Password');
    await user.type(input, 'NewPass123');
    await user.click(within(dialog).getByRole('button', { name: 'Reset Password' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/users/reset-password', {
        user_id: 10,
        new_password: 'NewPass123',
      }),
    );
  });

  it('shows an error banner when the student list fails to load', async () => {
    api.get.mockRejectedValue(new Error('offline'));
    render(<Students />);

    expect(await screen.findByText('errors.loadFailed')).toBeInTheDocument();
  });
});
