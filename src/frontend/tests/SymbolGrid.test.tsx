import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SymbolGrid } from '../src/components/symbols/SymbolGrid';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

const symbol = {
  id: 1,
  label: 'water',
  category: 'drinks',
  description: 'A glass of water',
  image_path: undefined,
  language: 'en',
  is_builtin: false,
  created_at: '2026-01-01',
  is_in_use: true,
};

describe('SymbolGrid', () => {
  it('renders symbols, selection, edit, delete, and pagination', () => {
    const onToggle = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onPreviousPage = vi.fn();
    const onNextPage = vi.fn();

    render(
      <SymbolGrid
        symbols={[symbol]}
        selectedIds={new Set([1])}
        onToggleSelection={onToggle}
        onEdit={onEdit}
        onDelete={onDelete}
        page={1}
        pageSize={10}
        onPreviousPage={onPreviousPage}
        onNextPage={onNextPage}
      />,
    );

    expect(screen.getByText('water')).toBeInTheDocument();
    expect(screen.getByText('drinks')).toBeInTheDocument();
    expect(screen.getByText('A glass of water')).toBeInTheDocument();

    const checkbox = screen.getByRole('checkbox', { name: /Select/ });
    expect(checkbox).toBeChecked();
    fireEvent.click(checkbox);
    expect(onToggle).toHaveBeenCalledWith(1, false);

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(onEdit).toHaveBeenCalledWith(symbol);

    fireEvent.click(screen.getByRole('button', { name: /Delete/ }));
    expect(onDelete).toHaveBeenCalledWith(1);

    fireEvent.click(screen.getByRole('button', { name: 'previous' }));
    expect(onPreviousPage).toHaveBeenCalled();
  });

  it('disables the previous button on the first page', () => {
    render(
      <SymbolGrid
        symbols={[symbol]}
        selectedIds={new Set()}
        onToggleSelection={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        page={0}
        pageSize={10}
        onPreviousPage={vi.fn()}
        onNextPage={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'previous' })).toBeDisabled();
  });
});
