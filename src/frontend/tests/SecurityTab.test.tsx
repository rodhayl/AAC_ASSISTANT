import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SecurityTab } from '../src/pages/Settings/SecurityTab';

const post = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    username: 'admin1',
    display_name: 'Admin',
    email: null as string | null,
    user_type: 'admin',
  },
}));

vi.mock('../src/lib/api', () => ({
  default: { post },
  extractError: (error: { message?: string } | undefined, fallback: string) =>
    error?.message || fallback,
}));

vi.mock('../src/store/authStore', () => {
  const useAuthStore = (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState;
  useAuthStore.setState = vi.fn();
  return { useAuthStore };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => {
      const table: Record<string, string> = {
        'security.title': 'Security',
        'security.change': 'Change password',
        'security.current': 'Current password',
        'security.new': 'New password',
        'security.confirm': 'Confirm password',
        'security.save': 'Save password',
        'security.saving': 'Saving…',
        'profile.cancel': 'Cancel',
      };
      return table[key] ?? defaultValue ?? key;
    },
  }),
}));

describe('SecurityTab', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('submits the password change with the user credentials', async () => {
    post.mockResolvedValue({});
    render(<SecurityTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'old-pass' },
    });
    fireEvent.change(screen.getByLabelText('New password'), {
      target: { value: 'new-pass' },
    });
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'new-pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save password' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/auth/change-password', {
        username: 'admin1',
        current_password: 'old-pass',
        new_password: 'new-pass',
        confirm_password: 'new-pass',
      }),
    );

    // The dialog closes and the form resets after a successful change.
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
  });

  it('keeps the dialog open and shows the server error when the change fails', async () => {
    post.mockRejectedValue(new Error('Current password is incorrect'));
    render(<SecurityTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'wrong' },
    });
    fireEvent.change(screen.getByLabelText('New password'), {
      target: { value: 'new-pass' },
    });
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'new-pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save password' }));

    await waitFor(() =>
      expect(screen.getByText('Current password is incorrect')).toBeInTheDocument(),
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('disables the submit button until every field is filled', () => {
    render(<SecurityTab />);
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));

    const submit = screen.getByRole('button', { name: 'Save password' });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'old-pass' },
    });
    fireEvent.change(screen.getByLabelText('New password'), {
      target: { value: 'new-pass' },
    });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'new-pass' },
    });
    expect(submit).toBeEnabled();
  });

  it('closes the dialog from the cancel button', () => {
    render(<SecurityTab />);
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes the dialog with the Escape key and restores focus to the trigger', () => {
    render(<SecurityTab />);
    const trigger = screen.getByRole('button', { name: 'Change password' });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });
});
