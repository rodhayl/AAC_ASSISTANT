import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SymbolPicker } from '../src/components/board/SymbolPicker';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));
const addToast = vi.hoisted(() => vi.fn());

vi.mock('../src/lib/api', () => ({
  default: api,
  extractError: (_error: unknown, fallback: string) => fallback,
}));

vi.mock('../src/store/toastStore', () => ({
  useToastStore: (selector?: (state: { addToast: typeof addToast }) => unknown) => {
    const state = { addToast };
    return selector ? selector(state) : state;
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../src/components/common/SymbolImage', () => ({
  SymbolImage: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

vi.mock('../src/components/ui/button', () => ({
  Button: ({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}));

vi.mock('../src/components/ui/icon-button', () => ({
  IconButton: ({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}));

vi.mock('../src/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: ReactNode }) => <div role="dialog">{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h1>{children}</h1>,
}));

vi.mock('../src/components/ui/select', () => ({
  Select: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  SelectValue: () => null,
}));

vi.mock('../src/lib/symbolCategoryStyle', () => ({
  getCategoryStyle: () => ({
    border: 'border',
    hoverBorder: 'hover-border',
    dot: 'dot',
  }),
}));

vi.mock('../src/lib/download', () => ({
  isValidImageFile: () => true,
}));

vi.mock('lucide-react', () => {
  const Icon = () => null;
  return {
    X: Icon,
    Search: Icon,
    ArrowUp: Icon,
    ArrowDown: Icon,
    Save: Icon,
  };
});

function symbol(id: number, label: string) {
  return {
    id,
    label,
    category: 'general',
    image_path: null,
  };
}

describe('SymbolPicker request ordering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('ignores a slow search response after a newer search completes', async () => {
    let resolveFirst: ((value: { data: unknown[] }) => void) | undefined;
    let symbolRequests = 0;
    api.get.mockImplementation((url: string) => {
      if (url === '/boards/symbols/categories') return Promise.resolve({ data: ['general'] });
      if (url === '/boards/symbols') {
        symbolRequests += 1;
        if (symbolRequests === 1) {
          return new Promise<{ data: unknown[] }>((resolve) => {
            resolveFirst = resolve;
          });
        }
        return Promise.resolve({ data: [symbol(2, 'Fresh')] });
      }
      return Promise.resolve({ data: [] });
    });

    render(
      <SymbolPicker
        isOpen
        onClose={vi.fn()}
        onSelect={vi.fn()}
        position={{ x: 0, y: 0 }}
      />,
    );

    await waitFor(() => expect(symbolRequests).toBe(1));
    fireEvent.change(screen.getByPlaceholderText('symbolPicker.searchPlaceholder'), {
      target: { value: 'new query' },
    });

    expect(await screen.findByText('Fresh')).toBeInTheDocument();
    await act(async () => {
      resolveFirst?.({ data: [symbol(1, 'Stale')] });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.queryByText('Stale')).not.toBeInTheDocument();
      expect(screen.getByText('Fresh')).toBeInTheDocument();
    });
  });
});
