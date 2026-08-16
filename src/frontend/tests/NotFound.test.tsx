import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NotFound } from '../src/pages/NotFound';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => {
      const map: Record<string, string> = {
        'errors.notFoundTitle': 'Página no encontrada',
        'errors.notFoundMessage': 'La página no existe o se ha movido.',
        'actions.backHome': 'Volver al inicio',
      };
      return map[key] || fallback || key;
    },
  }),
}));

vi.mock('react-router', () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));

describe('NotFound', () => {
  it('renders the localized title, message, and a home link', () => {
    render(<NotFound />);

    expect(screen.getByText('Página no encontrada')).toBeInTheDocument();
    expect(screen.getByText('La página no existe o se ha movido.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Volver al inicio' })).toHaveAttribute(
      'href',
      '/',
    );
  });
});
