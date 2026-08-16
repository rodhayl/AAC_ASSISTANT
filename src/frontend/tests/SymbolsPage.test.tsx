import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Symbols } from '../src/pages/Symbols';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  extractError: (_error: unknown, fallback: string) => fallback,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // Keys with an explicit fallback return the fallback text; keys without
    // one (placeholders, labels) resolve to the key itself so queries work.
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: 'en-US' },
  }),
}));

vi.mock('../src/components/ui/Button', () => ({
  Button: ({ children, ...props }: { children?: React.ReactNode }) => (
    <button type="button" {...props}>{children}</button>
  ),
}));

vi.mock('../src/components/ui/ConfirmDialog', () => ({
  ConfirmDialog: () => null,
}));

vi.mock('../src/components/symbols/SymbolGrid', () => ({
  SymbolGrid: () => <div data-testid="symbol-grid" />,
}));

const symbol = {
  id: 1,
  label: 'Cat',
  description: '',
  category: 'animals',
  keywords: '',
  language: 'en',
  is_builtin: true,
  created_at: '2026-01-01T00:00:00Z',
};

describe('Symbols page semantic search status', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the keyword-only banner when the server reports semantic search degraded', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: [symbol],
      headers: { 'x-semantic-search': 'degraded' },
    });

    render(<Symbols />);

    await waitFor(() => {
      expect(screen.getByTestId('semantic-search-status')).toBeInTheDocument();
    });
    expect(screen.getByTestId('semantic-search-status')).toHaveAttribute('role', 'status');
    expect(screen.getByTestId('semantic-search-status').textContent).toContain('keyword matches only');
  });

  it('does not show the banner when semantic search is enabled', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: [symbol],
      headers: { 'x-semantic-search': 'enabled' },
    });

    render(<Symbols />);

    await waitFor(() => expect(screen.getByTestId('symbol-grid')).toBeInTheDocument());
    expect(screen.queryByTestId('semantic-search-status')).not.toBeInTheDocument();
  });

  it('clears the banner once a later fetch reports no degradation', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({
        data: [symbol],
        headers: { 'x-semantic-search': 'degraded' },
      })
      .mockResolvedValueOnce({
        data: [symbol],
        headers: {},
      });

    render(<Symbols />);

    await waitFor(() => {
      expect(screen.getByTestId('semantic-search-status')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('searchSymbols'), {
      target: { value: 'cat' },
    });

    await waitFor(() => {
      expect(screen.queryByTestId('semantic-search-status')).not.toBeInTheDocument();
    });
  });
});
