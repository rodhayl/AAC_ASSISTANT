import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { Setup } from '../src/pages/Setup';
import { Login } from '../src/pages/Login';
import api from '../src/lib/api';
import { useAuthStore } from '../src/store/authStore';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  extractError: (e: unknown, fallback: string) => fallback,
}));

function makeJwt(exp: number, userId = 1) {
  const encode = (value: object) =>
    btoa(JSON.stringify(value))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

  return `${encode({ alg: 'none', typ: 'JWT' })}.${encode({
    sub: 'admin1',
    exp,
    user_id: userId,
  })}.signature`;
}

describe('Setup Page', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    });
    vi.mocked(api.get).mockResolvedValue({
      data: { setup_required: true, has_admin: false, app_name: 'AAC Assistant', app_version: '2.0.0' },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders initial setup form when setup is required', async () => {
    render(
      <MemoryRouter>
        <Setup />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /crear cuenta de administrador|create administrator/i })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/nombre de usuario|username/i)).toHaveValue('admin1');
  });

  it('submits valid admin setup and logs the user in', async () => {
    const fakeToken = makeJwt(Math.floor(Date.now() / 1000) + 3600);
    vi.mocked(api.post).mockResolvedValue({
      data: {
        message: 'Administrator created',
        user: {
          id: 1,
          username: 'admin1',
          display_name: 'Administrator',
          user_type: 'admin',
          is_active: true,
          created_at: '2026-01-01T00:00:00Z',
        },
        access_token: fakeToken,
        refresh_token: 'valid-refresh-token',
        token_type: 'bearer',
      },
    });

    render(
      <MemoryRouter>
        <Setup />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /crear cuenta de administrador|create administrator/i })).toBeInTheDocument();
    });

    const passInput = screen.getByLabelText(/^contraseña$|^password$/i);
    const confirmInput = screen.getByLabelText(/confirmar contraseña|confirm password/i);

    fireEvent.change(passInput, { target: { value: 'ValidStrongPass123!' } });
    fireEvent.change(confirmInput, { target: { value: 'ValidStrongPass123!' } });

    const submitBtn = screen.getByRole('button', { name: /crear cuenta de administrador|create administrator/i });
    expect(submitBtn).toBeEnabled();

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/setup', {
        username: 'admin1',
        display_name: 'Administrator',
        email: undefined,
        password: 'ValidStrongPass123!',
        confirm_password: 'ValidStrongPass123!',
      });
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
      expect(useAuthStore.getState().user?.username).toBe('admin1');
    });
  });

  it('redirects to /login when setup is not required', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { setup_required: false, has_admin: true, app_name: 'AAC Assistant', app_version: '2.0.0' },
    });

    render(
      <MemoryRouter initialEntries={['/setup']}>
        <Routes>
          <Route path="/setup" element={<Setup />} />
          <Route path="/login" element={<div>Login Page Target</div>} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Login Page Target')).toBeInTheDocument();
    });
  });

  it('automatically redirects Login to /setup when setup is required', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { setup_required: true, has_admin: false, app_name: 'AAC Assistant', app_version: '2.0.0' },
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/setup" element={<div>Setup Page Target</div>} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Setup Page Target')).toBeInTheDocument();
    });
  });
});
