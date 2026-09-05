import { act, fireEvent, render, screen } from '@testing-library/react'
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

// Base UI Select needs the jsdom polyfills from vitest.setup.ts; options are
// activated with pointerDown+click (userEvent/click-only hang or fail).
async function openSelectAndPick(triggerName: string, optionName: string) {
  const trigger = screen.getByRole('combobox', { name: triggerName })
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false })
  fireEvent.click(trigger)
  await act(async () => {})
  const option = screen.getByRole('option', { name: optionName })
  fireEvent.pointerDown(option, { button: 0, ctrlKey: false })
  fireEvent.click(option)
  await act(async () => {})
}

describe('SymbolEditorDialog', () => {
  beforeEach(() => {
    fetchBoards.mockReset()
  })

  it('excludes the current board from link targets and exposes dialog semantics', async () => {
    const onSave = vi.fn()
    render(
      <SymbolEditorDialog
        isOpen
        onClose={vi.fn()}
        onSave={onSave}
        symbol={symbol}
        currentBoardId={42}
      />,
    )

    expect(screen.getByRole('dialog', { name: 'editSymbol' })).toBeInTheDocument()
    expect(screen.getByLabelText('customLabel')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'close' })).toBeInTheDocument()
    expect(fetchBoards).toHaveBeenCalledTimes(1)

    // The trigger shows the current value (none); opening the popup lists only
    // the non-current boards.
    await openSelectAndPick('linkToBoard', 'Linked board')

    expect(screen.getByRole('dialog', { name: 'editSymbol' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Current board' })).not.toBeInTheDocument()

    // Selecting a board then saving passes its id to onSave.
    fireEvent.click(screen.getByRole('button', { name: 'save' }))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ linked_board_id: 43 }))
  })
})
