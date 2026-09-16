import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';
import type { BoardSymbol } from '../src/types';
const symbolRenderSpy = vi.hoisted(() => vi.fn());

vi.mock('../src/components/board/SymbolCard', async () => {
  const React = await vi.importActual<typeof import('react')>('react');

  return {
    SymbolCard: React.memo(function RenderSpySymbolCard({
      boardSymbol,
    }: {
      boardSymbol: BoardSymbol;
      onClick: (symbol: BoardSymbol) => void;
    }) {
      symbolRenderSpy(boardSymbol.id);
      return <button type="button">{boardSymbol.symbol.label}</button>;
    }),
  };
});

import { CommunicationGrid } from '../src/components/board/CommunicationGrid';
import { findNextOccupiedCellIndex } from '../src/lib/boardGrid';

const symbols: BoardSymbol[] = [
  {
    id: 1,
    symbol_id: 1,
    position_x: 0,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: {
      id: 1,
      label: 'Hello',
      image_path: '/hello.png',
      category: 'social',
      language: 'en',
      is_builtin: true,
      created_at: '',
    },
  },
  {
    id: 2,
    symbol_id: 2,
    position_x: 1,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: {
      id: 2,
      label: 'Eat',
      image_path: '/eat.png',
      category: 'actions',
      language: 'en',
      is_builtin: true,
      created_at: '',
    },
  },
];

const onSymbolClick = vi.fn();

function NavHarness() {
  return (
    <CommunicationGrid
      rows={3}
      cols={3}
      symbols={navSymbols}
      onSymbolClick={onSymbolClick}
    />
  );
}

// 3x3 grid with holes: Hello(0,0) Eat(2,0) Water(0,1) — cells 1, 5..8 empty.
const navSymbols: BoardSymbol[] = [
  symbols[0],
  { ...symbols[1], position_x: 2, position_y: 0 },
  {
    id: 3,
    symbol_id: 3,
    position_x: 0,
    position_y: 1,
    size: 1,
    is_visible: true,
    symbol: {
      id: 3,
      label: 'Water',
      image_path: '/water.png',
      category: 'food',
      language: 'en',
      is_builtin: true,
      created_at: '',
    },
  },
];

describe('CommunicationGrid arrow-key navigation', () => {
  it('walks to the next occupied cell, skipping empty ones', () => {
    render(<NavHarness />);
    const hello = screen.getByText('Hello');
    hello.focus();
    fireEvent.keyDown(hello, { key: 'ArrowRight' });
    expect(screen.getByText('Eat')).toHaveFocus();
  });

  it('keeps focus at the grid edge instead of scrolling the page', () => {
    render(<NavHarness />);
    const hello = screen.getByText('Hello');
    hello.focus();
    fireEvent.keyDown(hello, { key: 'ArrowLeft' });
    expect(hello).toHaveFocus();
  });

  it('moves vertically between occupied rows', () => {
    render(<NavHarness />);
    const hello = screen.getByText('Hello');
    hello.focus();
    fireEvent.keyDown(hello, { key: 'ArrowDown' });
    expect(screen.getByText('Water')).toHaveFocus();

    fireEvent.keyDown(screen.getByText('Water'), { key: 'ArrowUp' });
    expect(screen.getByText('Hello')).toHaveFocus();
  });

  it('findNextOccupiedCellIndex skips holes and stops at edges', () => {
    const occupied = [true, false, true, true, false, false, false, false, false];
    // From 0: right skips 1 and lands on 2.
    expect(findNextOccupiedCellIndex(0, 3, 3, 'ArrowRight', occupied)).toBe(2);
    // From 2: right hits the edge.
    expect(findNextOccupiedCellIndex(2, 3, 3, 'ArrowRight', occupied)).toBeNull();
    // From 0: down lands on 3.
    expect(findNextOccupiedCellIndex(0, 3, 3, 'ArrowDown', occupied)).toBe(3);
    // Non-arrow keys are ignored.
    expect(findNextOccupiedCellIndex(0, 3, 3, 'Enter', occupied)).toBeNull();
  });
});

function SearchHarness() {
  const [query, setQuery] = useState('');

  return (
    <>
      <label htmlFor="symbol-search">Search</label>
      <input
        id="symbol-search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <CommunicationGrid
        rows={1}
        cols={2}
        symbols={symbols}
        onSymbolClick={onSymbolClick}
      />
    </>
  );
}

describe('CommunicationGrid memoization', () => {
  it('does not rerender unchanged symbol cards when search state changes', () => {
    symbolRenderSpy.mockClear();
    onSymbolClick.mockClear();

    render(<SearchHarness />);
    expect(symbolRenderSpy.mock.calls.map(([id]) => id)).toEqual([1, 2]);

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'hello' } });

    expect(symbolRenderSpy.mock.calls.map(([id]) => id)).toEqual([1, 2]);
  });
});
