import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BoardSymbol } from '../src/types'
import { SymbolEditorDialog } from '../src/components/board/SymbolEditorDialog'

const fetchBoards = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}))

vi.mock('../src/store/boardStore', () => ({
  useBoardStore: (selector: (state: { boards: Array<{ id: number; name: string }>; fetchBoards: typeof fetchBoards }) => unknown) =>
    selector({
      boards: [
        { id: 42, name: 'Current board' },
        { id: 43, name: 'Linked board' },
      ],
      fetchBoards,
    }),
}))

const symbol: BoardSymbol = {
  id: 7,
  symbol_id: 9,
  position_x: 0,
  position_y: 0,
  size: 1,
  is_visible: true,
  symbol: {
    id: 9,
    label: 'Water',
    category: 'general',
    language: 'en',
    is_builtin: true,
    created_at: '2026-01-01T00:00:00Z',
  },
}

describe('SymbolEditorDialog', () => {
  beforeEach(() => {
    fetchBoards.mockReset()
  })

  it('excludes the current board from link targets and exposes dialog semantics', () => {
    render(
      <SymbolEditorDialog
        isOpen
        onClose={vi.fn()}
        onSave={vi.fn()}
        symbol={symbol}
        currentBoardId={42}
      />,
    )

    expect(screen.getByRole('dialog', { name: 'editSymbol' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Current board' })).not.toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Linked board' })).toBeInTheDocument()
    expect(screen.getByLabelText('customLabel')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
    expect(fetchBoards).toHaveBeenCalledTimes(1)
  })
})
