import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserManagementPage } from '../src/pages/UserManagement';
import api from '../src/lib/api';

const authState = {
  user: { id: 1, username: 'admin1', display_name: 'Admin', user_type: 'admin' as const },
};

vi.mock('../src/store/authStore', () => ({
  useAuthStore: () => authState,
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

vi.mock('react-router-dom', () => ({
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
    'actions.editAria': `Edit ${options?.name ?? ''}`,
    'actions.editTitle': 'Edit user',
    'actions.deleteAria': `Delete ${options?.name ?? ''}`,
    'actions.deleteTitle': 'Delete user',
    'actions.deleteConfirm': `Delete ${options?.name ?? ''}?`,
    'actions.resetPassword': 'Reset Pwd',
    'actions.resetPasswordAria': `Reset password for ${options?.name ?? ''}`,
    'actions.resetPasswordTitle': 'Reset Password',
    'resetPasswordTitle': `Reset Password for ${options?.name ?? ''}`,
    'profile.save': 'Save',
    'security.saving': 'Saving',
    'errors.passwordsDoNotMatch': 'Passwords do not match',
    'errors.deleteFailed': 'Failed to delete',
    'errors.deleteSelf': 'You cannot delete your own account',
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
    fireEvent.change(screen.getByLabelText('Username *'), { target: { value: 'teacher2' } });
    fireEvent.change(screen.getByLabelText('Display Name *'), { target: { value: 'Teacher Two' } });
    fireEvent.change(screen.getByLabelText('Password *'), { target: { value: 'Password1' } });
    fireEvent.change(screen.getByLabelText('Confirm Password *'), { target: { value: 'Password2' } });
    fireEvent.submit(screen.getByRole('dialog').querySelector('form')!);

    expect((await screen.findAllByText('Passwords do not match')).length).toBe(2);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('shows the backend self-delete error for the admin role', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [admin] } as never);
    vi.mocked(api.delete).mockRejectedValue({
      response: { status: 400, data: { detail: 'Cannot delete your own account' } },
    });

    render(<UserManagementPage role="admin" />);
    await screen.findByText('Admin');

    fireEvent.click(screen.getByRole('button', { name: 'Delete admin1' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/auth/users/1');
    });
    expect(await screen.findByText('Cannot delete your own account')).toBeInTheDocument();
  });
});
