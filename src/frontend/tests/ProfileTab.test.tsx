import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfileTab } from '../src/pages/Settings/ProfileTab';

const put = vi.hoisted(() => vi.fn());
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
  default: { put },
  extractError: (_err: unknown, fallback: string) => fallback,
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
        'profile.edit': 'Edit',
        'profile.cancel': 'Cancel',
        'profile.save': 'Save',
        'profile.displayName': 'Display Name',
        'profile.email': 'Email',
        'profile.updated': 'Profile updated successfully',
      };
      return table[key] ?? defaultValue ?? key;
    },
  }),
}));

describe('ProfileTab', () => {
  beforeEach(() => {
    put.mockReset();
    authState.user = { id: 1, username: 'admin1', display_name: 'Admin', email: null, user_type: 'admin' };
  });

  it('sends null for a blank email so saving the display name succeeds', async () => {
    put.mockResolvedValueOnce({
      data: { id: 1, username: 'admin1', display_name: 'New Admin', email: null },
    });

    render(<ProfileTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Display Name'), { target: { value: 'New Admin' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(put).toHaveBeenCalledWith('/auth/profile', { display_name: 'New Admin', email: null });
    });
  });

  it('trims and sends a non-empty email as-is', async () => {
    put.mockResolvedValueOnce({
      data: { id: 1, username: 'admin1', display_name: 'Admin', email: 'a@b.com' },
    });

    render(<ProfileTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: '  a@b.com  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(put).toHaveBeenCalledWith('/auth/profile', { display_name: 'Admin', email: 'a@b.com' });
    });
  });
});
