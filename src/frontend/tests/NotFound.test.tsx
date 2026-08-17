import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { NotFound } from '../src/pages/NotFound';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => defaultValue ?? key,
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
      screen.getByRole('link', { name: 'Go Back Home' }),
    ).toHaveAttribute('href', '/');
  });
});
