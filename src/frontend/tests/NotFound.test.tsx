import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { NotFound } from '../src/pages/NotFound';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) =>
      (globalThis as typeof globalThis & {
        __aacTestTranslation?: (namespace: string, key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) => string;
      }).__aacTestTranslation?.('error', key, arg2, arg3) ?? key,
  }),
}));

describe('NotFound page', () => {
  it('renders the translated title, message, and home link', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: 'Page Not Found' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/The page you are looking for doesn't exist/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Dashboard' }),
    ).toHaveAttribute('href', '/');
  });
});
