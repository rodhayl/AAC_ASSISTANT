import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';
import type { BoardSymbol } from '../src/types';
import { SymbolCard } from '../src/components/board/SymbolCard';

// Mock useTranslation
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, string>, arg3?: Record<string, string>) => {
      const options = typeof arg2 === 'object' ? arg2 : arg3;
      const defaults: Record<string, string> = {
        addToSentence: 'Add {{label}} to sentence',
        openFolder: 'Open folder {{label}}',
      };
      let text = typeof arg2 === 'string' ? arg2 : defaults[key] ?? key;
      for (const [name, value] of Object.entries(options || {})) {
        text = text.replace(`{{${name}}}`, value);
      }
      return text;
    },
  }),
}));

// Mock useAccessibleInteraction
vi.mock('../src/hooks/useAccessibleInteraction', () => ({
  useAccessibleInteraction: ({ onClick }: { onClick: () => void; disabled?: boolean }) => ({
    onClick,
  }),
}));

// Mock SymbolImage
vi.mock('../src/components/common/SymbolImage', () => ({
  SymbolImage: ({ imagePath, className }: { imagePath: string; className?: string }) => (
    <img data-testid="symbol-image" src={imagePath} className={className} alt="" />
  ),
}));

// Mock getCategoryStyle
vi.mock('../src/lib/symbolCategoryStyle', () => ({
  getCategoryStyle: () => ({
    border: 'border-blue-300',
    dot: 'bg-blue-400',
    hoverBorder: 'hover:border-blue-500',
  }),
}));

const baseSymbol: BoardSymbol = {
  id: 1,
  symbol_id: 10,
  position_x: 0,
  position_y: 0,
  size: 1,
  is_visible: true,
  symbol: {
    id: 10,
    label: 'Hello',
    image_path: '/hello.png',
    category: 'social',
    language: 'en',
    is_builtin: true,
    created_at: '2024-01-01',
  },
};

function renderSymbol(overrides: Partial<BoardSymbol> = {}, props: Record<string, unknown> = {}) {
  const symbol = { ...baseSymbol, ...overrides };
  return render(
    <SymbolCard
      boardSymbol={symbol}
      onClick={vi.fn()}
      {...props}
    />,
  );
}

describe('SymbolCard', () => {
  it('renders the symbol label', () => {
    renderSymbol();
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders custom_text when provided', () => {
    const symbol: BoardSymbol = {
      ...baseSymbol,
      custom_text: '¡Hola!',
    };
    render(<SymbolCard boardSymbol={symbol} onClick={vi.fn()} />);
    expect(screen.getByText('¡Hola!')).toBeInTheDocument();
    expect(screen.queryByText('Hello')).not.toBeInTheDocument();
  });

  it('renders an image when image_path is set', () => {
    renderSymbol();
    const img = screen.getByTestId('symbol-image');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', '/hello.png');
  });

  it('renders without an image when image_path is absent', () => {
    const symbol: BoardSymbol = {
      ...baseSymbol,
      symbol: { ...baseSymbol.symbol, image_path: '' },
    };
    render(<SymbolCard boardSymbol={symbol} onClick={vi.fn()} />);
    expect(screen.queryByTestId('symbol-image')).not.toBeInTheDocument();
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('shows a folder icon when linked_board_id is present', () => {
    const symbol: BoardSymbol = {
      ...baseSymbol,
      linked_board_id: 5,
    };
    const { container } = render(
      <SymbolCard boardSymbol={symbol} onClick={vi.fn()} />,
    );
    // Folder icon from lucide-react renders an SVG
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('applies background color when color is set', () => {
    const symbol: BoardSymbol = {
      ...baseSymbol,
      color: '#ff0000',
    };
    render(<SymbolCard boardSymbol={symbol} onClick={vi.fn()} />);
    const button = screen.getByRole('button');
    expect(button).toHaveStyle({ backgroundColor: '#ff0000' });
  });

  it('is disabled when the disabled prop is true', () => {
    renderSymbol({}, { disabled: true });
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(button.className).toMatch(/opacity-50/);
  });

  it('calls onClick with the board symbol when clicked', () => {
    const onClick = vi.fn();
    renderSymbol({}, { onClick });
    screen.getByRole('button').click();
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onClick).toHaveBeenCalledWith(expect.objectContaining({ id: 1, symbol_id: 10 }));
  });

  it('does not call onClick when disabled', () => {
    const onClick = vi.fn();
    render(<SymbolCard boardSymbol={baseSymbol} onClick={onClick} disabled={true} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('sets aria-label with the symbol label for sentence cards', () => {
    renderSymbol();
    expect(screen.getByRole('button')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Hello'),
    );
  });

  it('sets aria-label mentioning the folder for linked board cards', () => {
    const symbol: BoardSymbol = {
      ...baseSymbol,
      linked_board_id: 5,
    };
    render(<SymbolCard boardSymbol={symbol} onClick={vi.fn()} />);
    expect(screen.getByRole('button')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Open folder'),
    );
  });
});