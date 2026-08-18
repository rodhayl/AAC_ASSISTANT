import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';

import { Login } from '../src/pages/Login';

const authState = vi.hoisted(() => ({
  user: null,
  isLoading: false,
  error: null as string | null,
  login: vi.fn(async () => undefined),
}));

const api = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    (selector ? selector(authState) : authState) as ReturnType<typeof useAuthStore>,
}));

vi.mock('../src/lib/api', () => ({
  default: api,
}));

const tFn = (key: string, defaultValue?: string | { defaultValue?: string }) => {
  if (typeof defaultValue === 'string') return defaultValue;
  return defaultValue?.defaultValue ?? key;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tFn }),
}));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/setup" element={<div>setup-page</div>} />
        <Route path="/" element={<div>home-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Login page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = null;
    authState.isLoading = false;
    authState.error = null;
    authState.login.mockResolvedValue(undefined);
    api.get.mockResolvedValue({ data: { setup_required: false } });
  });

  it('renders the login form and checks the setup status', async () => {
    renderLogin();

    expect(screen.getByLabelText('username')).toBeInTheDocument();
    expect(screen.getByLabelText('password')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/auth/setup-status');
  });

  it('redirects to setup when an admin account is required', async () => {
    api.get.mockResolvedValue({ data: { setup_required: true } });
    renderLogin();

    expect(await screen.findByText('setup-page')).toBeInTheDocument();
  });

  it('logs in and navigates home', async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText('username'), 'admin1');
    await user.type(screen.getByLabelText('password'), 'Admin123');
    await user.click(screen.getByRole('button', { name: 'login' }));

    await waitFor(() => expect(authState.login).toHaveBeenCalledWith('admin1', 'Admin123'));
    expect(await screen.findByText('home-page')).toBeInTheDocument();
  });

  it('keeps the form visible when the setup check fails', async () => {
    api.get.mockRejectedValue(new Error('offline'));
    renderLogin();

    expect(await screen.findByLabelText('username')).toBeInTheDocument();
    expect(screen.queryByText('setup-page')).not.toBeInTheDocument();
  });

  it('shows the authentication error from the store', async () => {
    authState.error = 'Invalid credentials';
    renderLogin();

    expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
  });

  it('stays on the login page when authentication fails', async () => {
    const user = userEvent.setup();
    authState.login.mockRejectedValue(new Error('bad login'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderLogin();

    await user.type(screen.getByLabelText('username'), 'admin1');
    await user.type(screen.getByLabelText('password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'login' }));

    await waitFor(() => expect(authState.login).toHaveBeenCalled());
    expect(screen.getByLabelText('username')).toBeInTheDocument();
    expect(screen.queryByText('home-page')).not.toBeInTheDocument();
    consoleSpy.mockRestore();
  });
});
