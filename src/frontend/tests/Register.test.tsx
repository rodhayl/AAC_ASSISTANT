import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Register } from '../src/pages/Register';

const navigate = vi.fn();

vi.mock('react-router', () => ({
  useNavigate: () => navigate,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        title: 'Create account',
        subtitle: 'Register a student profile',
        username: 'Username',
        password: 'Password',
        displayName: 'Display name',
        teacherNote: 'Teachers are created by administrators.',
        create: 'Create account',
        back: 'Back to login',
        'placeholders.username': 'username',
        'placeholders.password': 'password',
        'placeholders.displayName': 'Display name',
      };
      return map[key] || key;
    },
  }),
}));

const storeState = vi.hoisted(() => ({
  register: vi.fn(),
  isLoading: false,
  error: null as string | null,
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof storeState) => unknown) =>
    selector ? selector(storeState) : storeState,
}));

describe('Register', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.error = null;
    storeState.isLoading = false;
    storeState.register.mockResolvedValue({});
  });

  it('submits the entered student credentials and navigates home', async () => {
    render(<Register />);

    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'student1' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'StrongPass123' },
    });
    fireEvent.change(screen.getByLabelText('Display name'), {
      target: { value: 'Sam Student' },
    });

    fireEvent.submit(screen.getByRole('button', { name: /Create account/ }));

    expect(storeState.register).toHaveBeenCalledWith({
      username: 'student1',
      password: 'StrongPass123',
      display_name: 'Sam Student',
      user_type: 'student',
    });

    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith('/'));
  });

  it('shows the store error without navigating', async () => {
    storeState.error = 'Username already registered';
    storeState.register.mockRejectedValue(new Error('taken'));

    render(<Register />);
    expect(screen.getByText('Username already registered')).toBeInTheDocument();

    fireEvent.submit(screen.getByRole('button', { name: /Create account/ }));
    expect(navigate).not.toHaveBeenCalled();
  });

  it('disables the submit button while loading', () => {
    storeState.isLoading = true;
    render(<Register />);
    expect(screen.getByRole('button', { name: /Create account/ })).toBeDisabled();
  });
});
