import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SymbolSearchModal } from '../src/components/board/SymbolSearchModal';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: { get: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) =>
      (globalThis as typeof globalThis & {
        __aacTestTranslation?: (namespace: string, key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) => string;
      }).__aacTestTranslation?.('boards', key, arg2, arg3) ?? key,
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
    // state and never re-queried). The Base UI select opens on pointer down
    // (userEvent's full pointer sequence hangs in jsdom, so drive it with
    // fireEvent directly).
    const categoryTrigger = screen.getByRole('combobox', { name: 'All Categories' });
    fireEvent.pointerDown(categoryTrigger, { button: 0, ctrlKey: false });
    fireEvent.click(categoryTrigger);
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    const animalsOption = screen.getByRole('option', { name: 'Animals' });
    fireEvent.pointerDown(animalsOption, { button: 0, ctrlKey: false });
    fireEvent.click(animalsOption);
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

    const languageTrigger = screen.getByRole('combobox', { name: 'All' });
    fireEvent.pointerDown(languageTrigger, { button: 0, ctrlKey: false });
    fireEvent.click(languageTrigger);
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    const spanishOption = screen.getByRole('option', { name: 'Spanish' });
    fireEvent.pointerDown(spanishOption, { button: 0, ctrlKey: false });
    fireEvent.click(spanishOption);
    await act(() => vi.advanceTimersByTimeAsync(200));
    await act(async () => { await Promise.resolve(); });
    expect(api.get).toHaveBeenLastCalledWith('/boards/symbols', expect.objectContaining({
      params: expect.objectContaining({ search: 'cat', language: 'es' }),
    }));
  });
});

describe('SymbolSearchModal pagination walk', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('walks every page instead of silently truncating at the first page', async () => {
    const page = (offset: number, count: number) =>
      Array.from({ length: count }, (_, i) => ({
        id: offset + i + 1,
        label: `Symbol ${offset + i + 1}`,
        category: 'general',
      }));
    vi.mocked(api.get).mockImplementation(
      (_url: string, config?: { params?: { skip?: number; limit?: number } }) => {
        // Mirror the backend contract: one request is capped at the requested
        // limit, and the walk must continue until a short page arrives.
        const skip = config?.params?.skip ?? 0;
        if (skip === 0) return Promise.resolve({ data: page(0, 1000) });
        return Promise.resolve({ data: page(1000, 5) });
      },
    );

    renderModal();
    const input = screen.getByPlaceholderText('Search for a symbol...');
    const form = input.closest('form')!;
    fireEvent.change(input, { target: { value: 'sym' } });
    fireEvent.submit(form);

    // A row beyond the first full 1000-item page must still be reachable: the
    // previous single-request implementation stopped at the first page and no
    // 'has more' signal ever surfaced the remaining results.
    await waitFor(
      () => {
        expect(screen.getByText('Symbol 1005')).toBeInTheDocument();
      },
      { timeout: 15000 },
    );
    const symbolCalls = vi.mocked(api.get).mock.calls.filter(
      ([url]) => url === '/boards/symbols',
    );
    expect(symbolCalls).toHaveLength(2);
    expect(symbolCalls[1][1]).toMatchObject({ params: { skip: 1000, limit: 1000 } });
  });
});
