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
    'savedTopics.title': 'Topics saved by teachers',
    'savedTopics.subtitle': 'Review and remove topics teachers have saved for their students.',
    'savedTopics.empty': 'No teacher has saved topics yet.',
    'savedTopics.topic': 'Topic',
    'savedTopics.board': 'Context',
    'savedTopics.teacher': 'Teacher',
    'savedTopics.savedAt': 'Saved',
    'savedTopics.delete': 'Delete',
    'savedTopics.deleteConfirm': 'Delete this saved topic?',
    'savedTopics.deleteSuccess': 'Topic deleted',
    'savedTopics.deleteFailed': 'Could not delete the topic',
    'savedTopics.loadFailed': 'Could not load saved topics',
    'savedTopics.searchPlaceholder': 'Search by topic, board, or teacher',
    'savedTopics.searchAria': 'Search saved topics',
    'savedTopics.total': `${options?.count ?? ''} topics in total`,
    'savedTopics.pageSize': `${options?.size ?? ''} per page`,
    'savedTopics.pageSizeAria': 'Topics per page',
    'savedTopics.prevPage': 'Previous',
    'savedTopics.nextPage': 'Next',
    'savedTopics.pageIndicator': `Page ${options?.page ?? ''} of ${options?.pages ?? ''}`,
    'savedTopics.actions.deleteTitle': 'Delete topic',
    'savedTopics.actions.deleteAria': `Delete topic ${options?.topic ?? ''}`,
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

const savedTopic = {
  id: 10,
  user_id: 2,
  board: 'El cielo',
  topic: 'Astronomía',
  created_by: 'Teacher One',
  created_at: '2026-01-05T00:00:00Z',
};

describe('UserManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The teachers page (admin) also fetches the saved-topics overview;
    // default it to empty so existing tests stay focused on user rows.
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.includes('/learning/topics/saved')) return { data: [] } as never;
      return { data: [teacher] } as never;
    });
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

  it('shows the admin saved-topics overview on the teachers page', async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.includes('/learning/topics/saved')) return { data: [savedTopic] } as never;
      return { data: [teacher] } as never;
    });
    render(<UserManagementPage role="teacher" />);

    expect(await screen.findByText('Topics saved by teachers')).toBeInTheDocument();
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/learning/topics/saved', {
        params: { scope: 'all', limit: 25, offset: 0 },
      }),
    );
    expect(await screen.findByText('Astronomía')).toBeInTheDocument();
    expect(screen.getByText('El cielo')).toBeInTheDocument();
    expect(screen.getAllByText('Teacher One').length).toBeGreaterThan(0);
  });

  it('deletes a saved topic through the admin view', async () => {
    let topicsAfterDelete = [savedTopic];
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.includes('/learning/topics/saved')) {
        return { data: topicsAfterDelete, headers: { 'x-total-count': String(topicsAfterDelete.length) } } as never;
      }
      return { data: [teacher] } as never;
    });
    vi.mocked(api.delete).mockImplementation(async () => {
      // Deleting the last topic empties the collection; the refetch must
      // observe that instead of re-listing the stale row.
      topicsAfterDelete = [];
      return {} as never;
    });
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Astronomía');
    await screen.findByText('Topics saved by teachers');

    fireEvent.click(screen.getByRole('button', { name: 'Delete topic Astronomía' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/learning/topics/saved/10'),
    );
    await waitFor(() => {
      expect(screen.queryByText('Astronomía')).not.toBeInTheDocument();
    });
  });

  it('does not show the saved-topics section on the admins page', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [admin] } as never);
    render(<UserManagementPage role="admin" />);
    await screen.findByText('Admin');

    expect(screen.queryByText('Topics saved by teachers')).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith('/learning/topics/saved', {
      params: { scope: 'all', limit: 25, offset: 0 },
    });
  });

  it('pages through saved topics with the page controls', async () => {
    // Two pages of 25: the mock serves the requested window from a 30-item
    // collection and reports the unpaginated total via the header.
    const collection = Array.from({ length: 30 }, (_, index) => ({
      ...savedTopic,
      id: 100 + index,
      topic: `Tema ${index + 1}`,
    }));
    vi.mocked(api.get).mockImplementation(async (url: string, config?: { params?: { limit?: number; offset?: number } }) => {
      if (url.includes('/learning/topics/saved')) {
        const { limit = 25, offset = 0 } = config?.params ?? {};
        return {
          data: collection.slice(offset, offset + (limit as number)),
          headers: { 'x-total-count': String(collection.length) },
        } as never;
      }
      return { data: [teacher] } as never;
    });
    render(<UserManagementPage role="teacher" />);

    await screen.findByText('Tema 1');
    expect(screen.getByTestId('saved-topics-total')).toHaveTextContent('30 topics in total');
    expect(screen.getByTestId('saved-topics-page-indicator')).toHaveTextContent('Page 1 of 2');
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await screen.findByText('Tema 26');
    expect(screen.getByTestId('saved-topics-page-indicator')).toHaveTextContent('Page 2 of 2');
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(screen.queryByText('Tema 1')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await screen.findByText('Tema 1');
    expect(screen.getByTestId('saved-topics-page-indicator')).toHaveTextContent('Page 1 of 2');
  });

  it('filters saved topics through the debounced search box', async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.includes('/learning/topics/saved')) {
        return { data: [savedTopic], headers: { 'x-total-count': '1' } } as never;
      }
      return { data: [teacher] } as never;
    });
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Astronomía');

    const searchBox = screen.getByLabelText('Search saved topics');
    fireEvent.change(searchBox, { target: { value: 'astro' } });

    // The request is debounced: nothing fires immediately.
    expect(api.get).not.toHaveBeenCalledWith('/learning/topics/saved', expect.objectContaining({
      params: expect.objectContaining({ search: 'astro' }),
    }));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/learning/topics/saved', {
        params: { scope: 'all', limit: 25, offset: 0, search: 'astro' },
      });
    });
  });

  it('changes the page size and returns to the first page', async () => {
    const collection = Array.from({ length: 30 }, (_, index) => ({
      ...savedTopic,
      id: 200 + index,
      topic: `Tema grande ${index + 1}`,
    }));
    vi.mocked(api.get).mockImplementation(async (url: string, config?: { params?: { limit?: number; offset?: number } }) => {
      if (url.includes('/learning/topics/saved')) {
        const { limit = 25, offset = 0 } = config?.params ?? {};
        return {
          data: collection.slice(offset, offset + (limit as number)),
          headers: { 'x-total-count': String(collection.length) },
        } as never;
      }
      return { data: [teacher] } as never;
    });
    render(<UserManagementPage role="teacher" />);
    await screen.findByText('Tema grande 1');

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await screen.findByText('Tema grande 26');

    fireEvent.change(screen.getByLabelText('Topics per page'), { target: { value: '50' } });
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/learning/topics/saved', {
        params: { scope: 'all', limit: 50, offset: 0 },
      });
    });
    expect(await screen.findByText('Tema grande 1')).toBeInTheDocument();
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
