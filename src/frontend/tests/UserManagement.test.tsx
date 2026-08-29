import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserManagementPage } from '../src/pages/UserManagement';
import api from '../src/lib/api';

const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'admin1', display_name: 'Admin', user_type: 'admin' as const },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  extractError: (error: { response?: { data?: { detail?: string } } }, fallback: string) =>
    error.response?.data?.detail || fallback,
}));

const navigate = vi.fn();

vi.mock('react-router', () => ({
  useNavigate: () => navigate,
}));

const translate = (key: string, options?: { name?: string }) => {
  const translations: Record<string, string> = {
    title: 'Teachers',
    subtitle: 'Manage teacher accounts',
    create: '+ Create Teacher',
    createTitle: 'Create New Teacher',
    createBtn: 'Create Teacher',
    edit: 'Edit',
    delete: 'Delete',
    cancel: 'Cancel',
    noTeachers: 'No teachers found',
    noAdmins: 'No admins found',
    you: 'You',
    'table.name': 'Name',
    'table.username': 'Username',
    'table.email': 'Email',
    'table.actions': 'Actions',
    'labels.username': 'Username *',
    'labels.displayName': 'Display Name *',
    'labels.email': 'Email',
    'labels.password': 'Password *',
    'labels.confirmPassword': 'Confirm Password *',
    'labels.newPassword': 'New Password',
    'labels.passwordHint': 'Password hint',
    'placeholders.username': 'e.g., teacher1',
    'placeholders.displayName': 'e.g., Mr. Smith',
    'placeholders.email': 'e.g., teacher@example.com',
    'actions.editAria': `Edit ${options?.name ?? ''}`,
    'actions.editTitle': 'Edit user',
    'actions.deleteAria': `Delete ${options?.name ?? ''}`,
    'actions.deleteTitle': 'Delete user',
    'actions.deleteSelfTitle': 'You cannot delete your own account',
    'deleteConfirm': `Delete ${options?.name ?? ''}?`,
    'actions.resetPassword': 'Reset Pwd',
    'actions.resetPasswordAria': `Reset password for ${options?.name ?? ''}`,
    'actions.resetPasswordTitle': 'Reset Password',
    'resetPasswordTitle': `Reset Password for ${options?.name ?? ''}`,
    'profile.save': 'Save',
    'security.saving': 'Saving',
    'errors.passwordsDoNotMatch': 'Passwords do not match',
    'errors.deleteFailed': 'Failed to delete',
    'errors.loadFailed': 'Failed to load teachers',
    'errors.updateFailed': 'Failed to update',
    'errors.createFailed': 'Failed to create teacher',
    'errors.resetPasswordFailed': 'Failed to reset password',
  };
  return translations[key] ?? key;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: translate }),
}));

const teacher = {
  id: 2,
  username: 'teacher1',
  display_name: 'Teacher One',
  email: 'teacher@example.com',
  user_type: 'teacher' as const,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

const admin = {
  id: 1,
  username: 'admin1',
  display_name: 'Admin',
  email: 'admin@example.com',
  user_type: 'admin' as const,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

describe('UserManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: [teacher] } as never);
  });

  it('loads the selected role and surfaces password validation before posting', async () => {
    render(<UserManagementPage role="teacher" />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/auth/users', {
        params: { limit: 1000, user_type: 'teacher' },
      });
    });
    expect(screen.getByText('Teacher One')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /\+ Create Teacher/ }));
    expect(screen.getByRole('dialog', { name: 'Create New Teacher' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Username *'), { target: { value: 'teacher2' } });
    fireEvent.change(screen.getByLabelText('Display Name *'), { target: { value: 'Teacher Two' } });
    fireEvent.change(screen.getByLabelText('Password *'), { target: { value: 'Password1' } });
    fireEvent.change(screen.getByLabelText('Confirm Password *'), { target: { value: 'Password2' } });
    fireEvent.submit(screen.getByRole('dialog').querySelector('form')!);

    expect((await screen.findAllByText('Passwords do not match')).length).toBe(2);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('disables the delete button for the current admin (self-delete)', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [admin] } as never);

    render(<UserManagementPage role="admin" />);
    await screen.findByText('Admin');

    const deleteButton = screen.getByRole('button', { name: 'Delete admin1' });
    expect(deleteButton).toBeDisabled();
    expect(deleteButton).toHaveAttribute('title', 'You cannot delete your own account');

    fireEvent.click(deleteButton);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('creates a teacher through the admin route', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: {} } as never);
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: /\+ Create Teacher/ }));
    const dialog = screen.getByRole('dialog', { name: 'Create New Teacher' });
    fireEvent.change(within(dialog).getByLabelText('Username *'), { target: { value: 'teacher2' } });
    fireEvent.change(within(dialog).getByLabelText('Display Name *'), { target: { value: 'Teacher Two' } });
    fireEvent.change(within(dialog).getByLabelText('Password *'), { target: { value: 'Password1' } });
    fireEvent.change(within(dialog).getByLabelText('Confirm Password *'), { target: { value: 'Password1' } });
    fireEvent.submit(dialog.querySelector('form')!);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/auth/admin/create-user', {
        username: 'teacher2',
        password: 'Password1',
        confirm_password: 'Password1',
        display_name: 'Teacher Two',
        email: undefined,
        user_type: 'teacher',
      }),
    );
  });

  it('creates an admin through the admin route', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: {} } as never);
    vi.mocked(api.get).mockResolvedValue({ data: [admin] } as never);
    render(<UserManagementPage role="admin" />);
    await screen.findByText('Admin');

    fireEvent.click(screen.getByRole('button', { name: /\+ Create/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Username *'), { target: { value: 'admin2' } });
    fireEvent.change(within(dialog).getByLabelText('Display Name *'), { target: { value: 'Admin Two' } });
    fireEvent.change(within(dialog).getByLabelText('Password *'), { target: { value: 'Password1' } });
    fireEvent.change(within(dialog).getByLabelText('Confirm Password *'), { target: { value: 'Password1' } });
    fireEvent.submit(dialog.querySelector('form')!);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/auth/admin/create-user', {
        username: 'admin2',
        password: 'Password1',
        confirm_password: 'Password1',
        display_name: 'Admin Two',
        email: undefined,
        user_type: 'admin',
      }),
    );
  });

  it('edits a teacher display name and email', async () => {
    vi.mocked(api.put).mockResolvedValue({
      data: { ...teacher, display_name: 'Renamed', email: 'new@example.com' },
    } as never);
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: 'Edit teacher1' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Display Name *'), { target: { value: 'Renamed' } });
    fireEvent.change(within(dialog).getByLabelText('Email'), { target: { value: 'new@example.com' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/auth/users/2', {
        display_name: 'Renamed',
        email: 'new@example.com',
      }),
    );
  });

  it('clearing the email field removes the stored email', async () => {
    vi.mocked(api.put).mockResolvedValue({
      data: { ...teacher, display_name: 'Teacher One', email: null },
    } as never);
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: 'Edit teacher1' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Email'), { target: { value: '' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    // The empty string is sent so the backend can normalize it to NULL;
    // sending undefined would silently keep the old email.
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/auth/users/2', {
        display_name: 'Teacher One',
        email: '',
      }),
    );
  });

  it('deletes a teacher after confirming', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: {} } as never);
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: 'Delete teacher1' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/auth/users/2'));
  });

  it('resets a teacher password from the modal', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: {} } as never);
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: 'Reset password for teacher1' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('New Password'), { target: { value: 'NewPass123' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reset Pwd' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/users/reset-password', {
        user_id: 2,
        new_password: 'NewPass123',
      }),
    );
  });

  it('shows an error when the user list fails to load', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(api.get).mockRejectedValue(new Error('offline'));
    render(<UserManagementPage role="teacher" />);

    expect(await screen.findByText('Failed to load teachers')).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it('shows the empty state when there are no users', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] } as never);
    render(<UserManagementPage role="teacher" />);

    expect(await screen.findByText('No teachers found')).toBeInTheDocument();
  });

  it('shows the you badge for the current admin', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [admin] } as never);
    render(<UserManagementPage role="admin" />);

    expect(await screen.findByText('You')).toBeInTheDocument();
  });

  it('closes the edit modal with the Escape key', async () => {
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: 'Edit teacher1' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.put).not.toHaveBeenCalled();
  });

  it('closes the create modal with the Escape key', async () => {
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: /\+ Create Teacher/ }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.post).not.toHaveBeenCalled();
  });

  it('shows an error when deleting a teacher fails', async () => {
    vi.mocked(api.delete).mockRejectedValue(new Error('delete down'));
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Teacher One');

    fireEvent.click(screen.getByRole('button', { name: 'Delete teacher1' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText('Failed to delete')).toBeInTheDocument();
  });
});
