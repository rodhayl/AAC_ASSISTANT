import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SymbolSearchModal } from '../src/components/board/SymbolSearchModal';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: { get: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
    i18n: { language: 'en-US' },
  }),
}));

vi.mock('../src/components/board/SymbolCard', () => ({
  SymbolCard: ({ boardSymbol, onClick }: { boardSymbol: { symbol: { label: string } }; onClick: () => void }) => (
    <button onClick={onClick}>{boardSymbol.symbol.label}</button>
  ),
}));

function renderModal() {
  return render(<SymbolSearchModal isOpen onClose={vi.fn()} onSelectSymbol={vi.fn()} />);
}

describe('SymbolSearchModal request lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('passes an AbortSignal and ignores stale results', async () => {
    let resolveFirst!: (value: unknown) => void;
    let resolveSecond!: (value: unknown) => void;
    vi.mocked(api.get)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));

    renderModal();
    const input = screen.getByPlaceholderText('Search for a symbol...');
    const form = input.closest('form')!;
    fireEvent.change(input, { target: { value: 'cat' } });
    await act(async () => { fireEvent.submit(form); });
    fireEvent.change(input, { target: { value: 'dog' } });
    await act(async () => { fireEvent.submit(form); });

    expect(vi.mocked(api.get).mock.calls).toHaveLength(2);
    const firstSignal = vi.mocked(api.get).mock.calls[0][1]?.signal as AbortSignal;
    expect(firstSignal).toBeInstanceOf(AbortSignal);
    await act(async () => { resolveSecond({ data: [{ id: 2, label: 'Dog', category: 'animals' }] }); });
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText('Dog')).toBeInTheDocument();
    expect(firstSignal.aborted).toBe(true);
    await act(async () => { resolveFirst({ data: [{ id: 1, label: 'Cat', category: 'animals' }] }); });

    expect(screen.queryByText('Cat')).not.toBeInTheDocument();
  });

  it('clears results and invalidates a pending search when the query is cleared', async () => {
    let resolveSearch!: (value: unknown) => void;
    vi.mocked(api.get).mockImplementation(() => new Promise((resolve) => { resolveSearch = resolve; }));

    renderModal();
    const input = screen.getByPlaceholderText('Search for a symbol...');
    const form = input.closest('form')!;
    fireEvent.change(input, { target: { value: 'cat' } });
    await act(async () => { fireEvent.submit(form); });
    fireEvent.change(input, { target: { value: '' } });
    await act(async () => { resolveSearch({ data: [{ id: 1, label: 'Stale cat', category: 'animals' }] }); });

    expect(screen.queryByText('Stale cat')).not.toBeInTheDocument();
  });

  it('debounces typing into one search request', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    renderModal();
    const input = screen.getByPlaceholderText('Search for a symbol...');
    fireEvent.change(input, { target: { value: 'c' } });
    fireEvent.change(input, { target: { value: 'ca' } });
    fireEvent.change(input, { target: { value: 'cat' } });

    expect(api.get).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(200));
    await act(async () => { await Promise.resolve(); });
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith('/boards/symbols', expect.objectContaining({
      params: expect.objectContaining({ search: 'cat' }),
    }));
  });

  it('re-runs the search when the category filter changes', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    renderModal();
    const input = screen.getByPlaceholderText('Search for a symbol...');
    fireEvent.change(input, { target: { value: 'cat' } });
    await act(() => vi.advanceTimersByTimeAsync(200));
    await act(async () => { await Promise.resolve(); });
    expect(api.get).toHaveBeenCalledTimes(1);

    // Picking a category must trigger a new search with the new filter,
    // not leave stale results on screen (regression: the change only set
    // state and never re-queried).
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'animals' } });
    await act(() => vi.advanceTimersByTimeAsync(200));
    await act(async () => { await Promise.resolve(); });
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', expect.objectContaining({
      params: expect.objectContaining({ search: 'cat', category: 'animals' }),
    }));
  });

  it('re-runs the search when the language filter changes', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    renderModal();
    const input = screen.getByPlaceholderText('Search for a symbol...');
    fireEvent.change(input, { target: { value: 'cat' } });
    await act(() => vi.advanceTimersByTimeAsync(200));
    await act(async () => { await Promise.resolve(); });

    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'es' } });
    await act(() => vi.advanceTimersByTimeAsync(200));
    await act(async () => { await Promise.resolve(); });
    expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', expect.objectContaining({
      params: expect.objectContaining({ search: 'cat', language: 'es' }),
    }));
  });
});
