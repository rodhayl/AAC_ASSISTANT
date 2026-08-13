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
