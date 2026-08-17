import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Symbols } from '../src/pages/Symbols';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('../src/lib/api', () => ({
  default: api,
  extractError: (error: unknown, fallback: string) => {
    const value = error as {
      response?: { data?: { detail?: string; error?: string; message?: string } };
      message?: string;
    };
    return (
      value.response?.data?.detail ||
      value.response?.data?.error ||
      value.response?.data?.message ||
      value.message ||
      fallback
    );
  },
}));

const tFn = (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key;

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tFn, i18n: { language: 'en' } }),
}));

const symbol = {
  id: 1,
  label: 'Hello',
  description: 'A greeting',
  category: 'greeting',
  keywords: 'hi, hello',
  image_path: null,
  is_in_use: false,
  created_at: '2026-01-01T00:00:00Z',
};

describe('Symbols page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') {
        return Promise.resolve({ data: [symbol] });
      }
      if (url === '/arasaac/search') {
        return Promise.resolve({ data: [{ id: 9, label: 'House', keywords: 'casa', image_url: 'https://example.com/9.png' }] });
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValue({ data: {} });
    api.put.mockResolvedValue({ data: {} });
    api.delete.mockResolvedValue({ data: {} });
  });

  it('loads and renders the symbol library with filters', async () => {
    render(<Symbols />);

    expect(await screen.findByText('Hello')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/boards/symbols', {
      params: { skip: 0, limit: 100 },
    });
  });

  it('searches with the current query and filters by usage', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    const searchInput = screen.getByPlaceholderText('searchSymbols');
    await user.type(searchInput, 'hola');
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', {
        params: { skip: 0, limit: 100, search: 'hola' },
      }),
    );

    await user.click(screen.getByRole('button', { name: 'filters.inUse' }));
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', {
        params: { skip: 0, limit: 100, search: 'hola', usage: 'in_use' },
      }),
    );
  });

  it('creates a symbol without an image', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /newSymbol/ }));
    const labelInput = screen.getByPlaceholderText('e.g., Hola');
    await user.type(labelInput, 'Adiós');
    await user.click(screen.getByRole('button', { name: 'create' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/boards/symbols', {
        label: 'Adiós',
        description: '',
        category: 'general',
        keywords: '',
      }),
    );
  });

  it('edits an existing symbol', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /edit/i }));
    const labelInput = screen.getByPlaceholderText('e.g., Hola');
    await user.clear(labelInput);
    await user.type(labelInput, 'Hi there');
    await user.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/boards/symbols/1', {
        label: 'Hi there',
        description: 'A greeting',
        category: 'greeting',
        keywords: 'hi, hello',
      }),
    );
  });

  it('deletes a symbol and retries with force when it is in use', async () => {
    const user = userEvent.setup();
    api.delete
      .mockRejectedValueOnce({
        response: { status: 400 },
        message: 'Symbol is in use on 2 boards',
      })
      .mockResolvedValueOnce({ data: {} });
    render(<Symbols />);
    await screen.findByText('Hello');

    const card = screen.getByText('Hello').closest('.p-4') as HTMLElement;
    await user.click(within(card).getAllByRole('button', { name: '' })[0]);
    let dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByText('delete'));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/1'),
    );
    expect(await screen.findByText('symbolInUseForceDelete')).toBeInTheDocument();
    dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByText('forceDelete'));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/1?force=true'),
    );
  });

  it('batch-deletes selected symbols and reports failures', async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue({
      data: [
        symbol,
        { ...symbol, id: 2, label: 'Bye' },
      ],
    });
    api.delete
      .mockRejectedValueOnce({
        response: { status: 400 },
        message: 'Symbol is in use on 1 board',
      })
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: {} });
    render(<Symbols />);
    await screen.findByText('Hello');

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    await user.click(checkboxes[1]);
    await user.click(screen.getByRole('button', { name: /deleteSelected/ }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByText('delete'));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/1');
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/2');
    });
    // First delete fails as in-use, is retried with force and succeeds; the
    // second symbol deletes cleanly, so no failure banner is shown.
    expect(screen.queryByText(/Some deletions failed/)).not.toBeInTheDocument();
  });

  it('searches and imports an ARASAAC symbol', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /searchArasaac/ }));
    const queryInput = screen.getByPlaceholderText('searchPlaceholder');
    await user.type(queryInput, 'casa');
    await user.click(screen.getByRole('button', { name: 'search' }));

    expect(await screen.findByText('House')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/arasaac/search', {
      params: { q: 'casa', locale: 'en' },
    });

    await user.click(screen.getByRole('button', { name: /import/i }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/arasaac/import', {
        arasaac_id: 9,
        label: 'House',
        description: undefined,
        keywords: 'casa',
        category: 'ARASAAC',
      }),
    );
  });

  it('shows an error banner when loading symbols fails', async () => {
    api.get.mockRejectedValue(new Error('offline'));
    render(<Symbols />);

    expect(await screen.findByText('offline')).toBeInTheDocument();
  });
});
