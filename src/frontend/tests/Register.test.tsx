import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Register } from '../src/pages/Register';

const register = vi.hoisted(() => vi.fn());
const navigate = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  register,
  isLoading: false,
  error: null as string | null,
}));

vi.mock('../src/store/authStore', () => {
  const useAuthStore = (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState;
  useAuthStore.setState = vi.fn();
  return { useAuthStore };
});

vi.mock('react-router', () => ({
  useNavigate: () => navigate,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => {
      const table: Record<string, string> = {
        title: 'Create account',
        subtitle: 'Join as a student',
        username: 'Username',
        password: 'Password',
        displayName: 'Display name',
        create: 'Create account',
        back: 'Back to login',
      };
      return table[key] ?? defaultValue ?? key;
    },
  }),
}));

describe('Register page', () => {
  beforeEach(() => {
    register.mockReset();
    navigate.mockReset();
    authState.isLoading = false;
    authState.error = null;
  });

  it('registers a student account and navigates home', async () => {
    register.mockResolvedValue({});
    render(<Register />);

    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'new_student' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'StudentPass123' },
    });
    fireEvent.change(screen.getByLabelText('Display name'), {
      target: { value: 'New Student' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() =>
      expect(register).toHaveBeenCalledWith({
        username: 'new_student',
        password: 'StudentPass123',
        display_name: 'New Student',
        user_type: 'student',
      }),
    );
    expect(navigate).toHaveBeenCalledWith('/');
  });

  it('stays on the page when registration fails', async () => {
    register.mockRejectedValue(new Error('username taken'));
    render(<Register />);

    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'taken' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'StudentPass123' },
    });
    fireEvent.change(screen.getByLabelText('Display name'), {
      target: { value: 'Taken' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => expect(register).toHaveBeenCalled());
    expect(navigate).not.toHaveBeenCalled();
  });

  it('shows the store error message and disables the submit while loading', () => {
    authState.error = 'Username already exists';
    authState.isLoading = true;
    render(<Register />);

    expect(screen.getByText('Username already exists')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Create account' }),
    ).toBeDisabled();
  });
});
