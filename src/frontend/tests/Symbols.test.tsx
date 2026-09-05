import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Symbols } from '../src/pages/Symbols';
import { act } from 'react';

const t = (key: string) => key;

// Base UI Select jsdom interaction: open via pointerDown+click, commit an
// option the same way (see SymbolSearchModal.test.tsx for the proven pattern).
// After committing, wait until the popup has fully closed so the next
// select's trigger click is not swallowed by the closing popup.
async function pickSelectOption(triggerName: string, optionName: string) {
  const trigger = screen.getByRole('combobox', { name: triggerName });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(trigger);
  const option = await screen.findByRole('option', { name: optionName });
  fireEvent.pointerDown(option, { button: 0, ctrlKey: false });
  fireEvent.click(option);
  await act(async () => {});
  await waitFor(() => expect(screen.queryByRole('option')).not.toBeInTheDocument());
}

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

const addToast = vi.hoisted(() => vi.fn());

vi.mock('../src/store/toastStore', () => ({
  useToastStore: (selector?: (s: { addToast: typeof addToast }) => unknown) => {
    const state = { addToast };
    return selector ? selector(state) : state;
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
    class FakeFileReader {
      result = 'data:image/png;base64,abc';
      onload: (() => void) | null = null;
      readAsDataURL() {
        this.onload?.();
      }
    }
    vi.stubGlobal('FileReader', FakeFileReader);
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

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads and renders the symbol library with filters', async () => {
    render(<Symbols />);

    expect(await screen.findByText('Hello')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/boards/symbols', {
      params: { skip: 0, limit: 101 },
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
        params: { skip: 0, limit: 101, search: 'hola' },
      }),
    );

    await user.click(screen.getByRole('button', { name: 'filters.inUse' }));
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', {
        params: { skip: 0, limit: 101, search: 'hola', usage: 'in_use' },
      }),
    );
  });

  it('creates a symbol without an image', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /newSymbol/ }));
    const labelInput = screen.getByPlaceholderText('labelPlaceholder');
    await user.type(labelInput, 'Adiós');
    await user.click(screen.getByRole('button', { name: 'create' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/boards/symbols', {
        label: 'Adiós',
        description: '',
        category: 'general',
        keywords: '',
        language: 'en',
      }),
    );
  });

  it('edits an existing symbol', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /edit/i }));
    const labelInput = screen.getByPlaceholderText('labelPlaceholder');
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
        message: 'Symbol is in use on 2 boards; remove or use force=true',
      })
      .mockResolvedValueOnce({ data: {} });
    render(<Symbols />);
    await screen.findByText('Hello');

    const card = screen.getByText('Hello').closest('.p-4') as HTMLElement;
    await user.click(within(card).getByRole('button', { name: 'deleteSymbol' }));
    let dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByText('delete'));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/1'),
    );
    expect(await screen.findByText('symbolInUseForceDelete')).toBeInTheDocument();
    dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByText('forceDelete'));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/1?force=true'),
    );
  });

  it('batch-deletes symbols and skips in-use ones without force-deleting them', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation((url: string) =>
      url === '/boards/symbols'
        ? Promise.resolve({ data: [symbol, { ...symbol, id: 2, label: 'Bye' }] })
        : Promise.resolve({ data: [] }),
    );
    api.delete
      .mockRejectedValueOnce({
        response: { status: 400 },
        message: 'El símbolo está en uso en tableros; elimine o use force=true',
      })
      .mockResolvedValueOnce({ data: {} });
    render(<Symbols />);
    await screen.findByText('Hello');

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    await user.click(checkboxes[1]);
    await user.click(screen.getByRole('button', { name: /deleteSelected/ }));

    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByText('delete'));

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/1');
      expect(api.delete).toHaveBeenCalledWith('/boards/symbols/2');
    });
    // The in-use symbol is reported (localized backend message with the
    // force=true marker) but never force-deleted in a batch; the clean one
    // deletes normally and the banner explains what was skipped.
    expect(api.delete).not.toHaveBeenCalledWith('/boards/symbols/1?force=true');
    expect(await screen.findByText(/batchDeleteInUseSkipped/)).toBeInTheDocument();
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

  it('filters by category and changes the sort order', async () => {
    render(<Symbols />);
    await screen.findByText('Hello');

    await pickSelectOption(t('filters.category'), 'greeting');
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', {
        params: { skip: 0, limit: 101, category: 'greeting' },
      }),
    );

    // Options are named by their (mocked, key-returning) translated labels.
    await pickSelectOption(t('filters.sort'), t('filters.newest'));
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', {
        params: { skip: 0, limit: 101, category: 'greeting', sort: 'newest' },
      }),
    );
  });

  it('ignores a stale response when a newer fetch supersedes it', async () => {
    const user = userEvent.setup();
    let resolveFirst!: (value: unknown) => void;
    // Queue responses per /boards/symbols call; the mount-time categories
    // fetch must resolve to [] without consuming the chain below.
    const symbolResponses = [
      new Promise((resolve) => {
        resolveFirst = resolve;
      }),
      Promise.resolve({ data: [{ ...symbol, id: 2, label: 'Fresh' }] }),
    ];
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') return symbolResponses.shift() ?? Promise.resolve({ data: [symbol] });
      return Promise.resolve({ data: [] });
    });
    const symbolsCalls = () => api.get.mock.calls.filter(([u]) => u === '/boards/symbols');
    render(<Symbols />);
    await waitFor(() => expect(symbolsCalls()).toHaveLength(1));

    await user.type(screen.getByPlaceholderText('searchSymbols'), 'x');
    await waitFor(() => expect(symbolsCalls()).toHaveLength(2));
    expect(await screen.findByText('Fresh')).toBeInTheDocument();

    resolveFirst({ data: [{ ...symbol, id: 3, label: 'Stale' }] });
    await waitFor(() => expect(screen.queryByText('Stale')).not.toBeInTheDocument());
    expect(screen.getByText('Fresh')).toBeInTheDocument();
  });

  it('ignores a stale error when a newer fetch supersedes it', async () => {
    const user = userEvent.setup();
    let rejectFirst!: (reason: unknown) => void;
    const symbolResponses = [
      new Promise((_, reject) => {
        rejectFirst = reject;
      }),
      Promise.resolve({ data: [{ ...symbol, id: 2, label: 'Fresh' }] }),
    ];
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') return symbolResponses.shift() ?? Promise.resolve({ data: [symbol] });
      return Promise.resolve({ data: [] });
    });
    const symbolsCalls = () => api.get.mock.calls.filter(([u]) => u === '/boards/symbols');
    render(<Symbols />);
    await waitFor(() => expect(symbolsCalls()).toHaveLength(1));

    await user.type(screen.getByPlaceholderText('searchSymbols'), 'x');
    await waitFor(() => expect(symbolsCalls()).toHaveLength(2));
    expect(await screen.findByText('Fresh')).toBeInTheDocument();

    rejectFirst(new Error('stale error'));
    await waitFor(() => expect(screen.queryByText('stale error')).not.toBeInTheDocument());
    expect(screen.getByText('Fresh')).toBeInTheDocument();
  });

  it('edits a symbol and uploads a replacement image', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /edit/i }));
    const fileInput = screen.getByLabelText('upload');
    await user.upload(fileInput, new File(['image-bytes'], 'pic.png', { type: 'image/png' }));

    await user.click(screen.getByRole('button', { name: 'save' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/boards/symbols/1', {
        label: 'Hello',
        description: 'A greeting',
        category: 'greeting',
        keywords: 'hi, hello',
      }),
    );
    expect(api.post).toHaveBeenCalledWith('/boards/symbols/1/image', expect.any(FormData));
  });

  it('creates a symbol with an uploaded image and full metadata', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /newSymbol/ }));
    const labelInput = screen.getByPlaceholderText('labelPlaceholder');
    await user.type(labelInput, 'Adiós');
    await user.type(screen.getByPlaceholderText('optionalDesc'), 'A farewell');
    await user.type(screen.getByPlaceholderText('commaSeparated'), 'bye, adios');
    await pickSelectOption(t('category'), 'greeting');
    const fileInput = screen.getByLabelText('upload');
    await user.upload(fileInput, new File(['image-bytes'], 'pic.png', { type: 'image/png' }));

    await user.click(screen.getByRole('button', { name: 'create' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/boards/symbols/upload', expect.any(FormData)),
    );
  });

  it('shows an error when creating a symbol fails', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue(new Error('create down'));
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /newSymbol/ }));
    await user.type(screen.getByPlaceholderText('labelPlaceholder'), 'Adiós');
    await user.click(screen.getByRole('button', { name: 'create' }));

    expect(await screen.findByText('create down')).toBeInTheDocument();
  });

  it('shows an error when updating a symbol fails', async () => {
    const user = userEvent.setup();
    api.put.mockRejectedValue(new Error('update down'));
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: 'save' }));

    expect(await screen.findByText('update down')).toBeInTheDocument();
  });

  it('rejects a non-image file with an error message', async () => {
    render(<Symbols />);
    await screen.findByText('Hello');

    const fileInput = screen.getByLabelText('upload');
    fireEvent.change(fileInput, {
      target: { files: [new File(['text'], 'note.txt', { type: 'text/plain' })] },
    });

    expect(screen.getByText('invalidFile')).toBeInTheDocument();
  });

  it('clears the selected file when the input is emptied', async () => {
    render(<Symbols />);
    await screen.findByText('Hello');

    const fileInput = screen.getByLabelText('upload');
    fireEvent.change(fileInput, { target: { files: [] } });

    expect(screen.getByText('upload')).toBeInTheDocument();
  });

  it('does not search ARASAAC with an empty query', async () => {
    render(<Symbols />);
    await screen.findByText('Hello');

    fireEvent.click(screen.getByRole('button', { name: /searchArasaac/ }));
    const queryInput = screen.getByPlaceholderText('searchPlaceholder');
    fireEvent.submit(queryInput.closest('form') as HTMLFormElement);

    expect(api.get).not.toHaveBeenCalledWith('/arasaac/search', expect.anything());
  });

  it('shows an error when the ARASAAC search fails', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols') {
        return Promise.resolve({ data: [symbol] });
      }
      if (url === '/arasaac/search') {
        return Promise.reject(new Error('arasaac down'));
      }
      return Promise.resolve({ data: [] });
    });
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /searchArasaac/ }));
    await user.type(screen.getByPlaceholderText('searchPlaceholder'), 'casa');
    await user.click(screen.getByRole('button', { name: 'search' }));

    expect(await screen.findByText('arasaacSearchFailed')).toBeInTheDocument();
  });

  it('shows a success toast after importing an ARASAAC symbol', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /searchArasaac/ }));
    await user.type(screen.getByPlaceholderText('searchPlaceholder'), 'casa');
    await user.click(screen.getByRole('button', { name: 'search' }));
    await screen.findByText('House');
    await user.click(screen.getByRole('button', { name: /import/i }));

    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith('importSuccess', 'success'),
    );
  });

  it('shows an error when importing an ARASAAC symbol fails', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue(new Error('import down'));
    render(<Symbols />);
    await screen.findByText('Hello');

    await user.click(screen.getByRole('button', { name: /searchArasaac/ }));
    await user.type(screen.getByPlaceholderText('searchPlaceholder'), 'casa');
    await user.click(screen.getByRole('button', { name: 'search' }));
    await screen.findByText('House');
    await user.click(screen.getByRole('button', { name: /import/i }));

    expect(await screen.findByText('importFailed')).toBeInTheDocument();
  });

  it('cancels the delete dialog without deleting', async () => {
    const user = userEvent.setup();
    render(<Symbols />);
    await screen.findByText('Hello');

    const card = screen.getByText('Hello').closest('.p-4') as HTMLElement;
    await user.click(within(card).getByRole('button', { name: 'deleteSymbol' }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByText('cancel'));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('skips an in-use symbol in a batch without any force retry', async () => {
    const user = userEvent.setup();
    api.delete.mockRejectedValueOnce({
      response: { status: 400 },
      message: 'Symbol is in use on 1 board; remove or use force=true',
    });
    render(<Symbols />);
    await screen.findByText('Hello');

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    await user.click(screen.getByRole('button', { name: /deleteSelected/ }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByText('delete'));

    expect(api.delete).toHaveBeenCalledWith('/boards/symbols/1');
    expect(api.delete).not.toHaveBeenCalledWith('/boards/symbols/1?force=true');
    expect(await screen.findByText(/batchDeleteInUseSkipped/)).toBeInTheDocument();
  });

  it('reports a batch failure when a symbol cannot be deleted', async () => {
    const user = userEvent.setup();
    api.delete.mockRejectedValueOnce({
      response: { status: 400 },
      message: 'Cannot delete core symbol',
    });
    render(<Symbols />);
    await screen.findByText('Hello');

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    await user.click(screen.getByRole('button', { name: /deleteSelected/ }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByText('delete'));

    expect(await screen.findByText(/someDeletionsFailed/)).toBeInTheDocument();
  });

  it('shows an error when a single delete fails for another reason', async () => {
    const user = userEvent.setup();
    api.delete.mockRejectedValue(new Error('offline'));
    render(<Symbols />);
    await screen.findByText('Hello');

    const card = screen.getByText('Hello').closest('.p-4') as HTMLElement;
    await user.click(within(card).getByRole('button', { name: 'deleteSymbol' }));
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByText('delete'));

    expect(await screen.findByText('offline')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });

  it('deselects a symbol when its checkbox is toggled off', async () => {
    const user = userEvent.setup();
    api.get.mockImplementation((url: string) =>
      url === '/boards/symbols'
        ? Promise.resolve({ data: [symbol, { ...symbol, id: 2, label: 'Bye' }] })
        : Promise.resolve({ data: [] }),
    );
    render(<Symbols />);
    await screen.findByText('Hello');

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    expect(screen.getByRole('button', { name: /deleteSelected/ })).toBeEnabled();

    await user.click(checkboxes[0]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /deleteSelected/ })).toBeDisabled(),
    );
  });

  it('paginates through the symbol library', async () => {
    // Rendering 100+ instrumented cards is slow under coverage, so this test
    // gets a longer budget than the default 5s.
    const user = userEvent.setup();
    const many = Array.from({ length: 101 }, (_, i) => ({
      ...symbol,
      id: i + 1,
      label: `Symbol ${i + 1}`,
    }));
    api.get.mockImplementation((url: string, options?: { params?: { skip?: number } }) => {
      if (url === '/boards/symbols') {
        const skip = options?.params?.skip ?? 0;
        return Promise.resolve({ data: many.slice(skip, skip + 101) });
      }
      return Promise.resolve({ data: [] });
    });
    render(<Symbols />);
    await screen.findByText('Symbol 1');

    await user.click(screen.getByRole('button', { name: 'next' }));
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', {
        params: { skip: 100, limit: 101 },
      }),
    );
    expect(await screen.findByText('Symbol 101')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'previous' }));
    expect(await screen.findByText('Symbol 1')).toBeInTheDocument();
  }, 20000);
});
