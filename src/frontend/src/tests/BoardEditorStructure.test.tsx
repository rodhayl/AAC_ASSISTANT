import { act, render, renderHook, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AISuggestionPanel } from '../components/board/AISuggestionPanel';
import { useBoardCollab } from '../hooks/useBoardCollab';
import { getBoardPlayabilityStatus, mergeBoardSymbols } from '../pages/boardEditorUtils';
import type { Board, BoardSymbol } from '../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string, options?: Record<string, unknown>) => {
      if (key === 'boardFullWarning') return `${key}:${options?.rows}x${options?.cols}`;
      return fallback || key;
    },
  }),
}));

class MockWebSocket {
  static readonly OPEN = 1;
  static readonly instances: MockWebSocket[] = [];
  readonly url: string;
  readonly send = vi.fn();
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  receive(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}

const symbol = (id: number, label: string): BoardSymbol => ({
  id,
  symbol_id: id,
  position_x: 0,
  position_y: 0,
  size: 1,
  is_visible: true,
  symbol: {
    id,
    label,
    category: 'general',
    language: 'en',
    is_builtin: true,
    created_at: '2026-01-01T00:00:00Z',
  },
});

const board = {
  id: 1,
  user_id: 1,
  name: 'Test board',
  category: 'general',
  is_public: false,
  is_template: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  grid_rows: 4,
  grid_cols: 5,
  symbols: [symbol(1, 'Apple')],
} satisfies Board;

describe('BoardEditor structure', () => {
  beforeEach(() => {
    MockWebSocket.instances.length = 0;
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  it('merges unsaved symbol overrides without delaying the board snapshot', () => {
    const merged = mergeBoardSymbols(board.symbols, {
      1: { position_x: 3, position_y: 2, custom_text: 'Fruit' },
    });

    expect(merged).toEqual([
      expect.objectContaining({
        id: 1,
        position_x: 3,
        position_y: 2,
        custom_text: 'Fruit',
      }),
    ]);
    expect(board.symbols[0]).toEqual(symbol(1, 'Apple'));
  });

  it('calculates the 50-percent playability threshold with a ceiling', () => {
    const status = getBoardPlayabilityStatus(
      { ...board, grid_rows: 3, grid_cols: 3 },
      [
        symbol(1, 'One'),
        symbol(2, 'Two'),
        symbol(3, 'Three'),
        symbol(4, 'Four'),
        symbol(5, 'Five'),
      ],
    );

    expect(status).toMatchObject({
      playable: true,
      count: 5,
      threshold: 5,
      needed: 0,
    });
  });

  it('connects with an encoded token, broadcasts local moves, and reports remote moves', () => {
    const onRemoteMove = vi.fn();
    const { result, unmount } = renderHook(() =>
      useBoardCollab({ boardId: 42, token: 'token with spaces', onRemoteMove }),
    );
    const socket = MockWebSocket.instances[0];

    expect(socket.url).toContain('/collab/boards/42?token=token%20with%20spaces');
    socket.open();

    act(() => {
      result.current.sendMove(7, { x: 2, y: 3 });
    });
    expect(socket.send).toHaveBeenCalledWith(JSON.stringify({
      op: 'move',
      symbol_id: 7,
      position: { x: 2, y: 3 },
    }));

    act(() => {
      socket.receive({
        type: 'board_change',
        payload: { op: 'move', symbol_id: 7, position: { x: 4, y: 1 } },
      });
    });
    expect(onRemoteMove).toHaveBeenCalledWith(7, { x: 4, y: 1 });

    unmount();
    expect(socket.readyState).toBe(3);
  });

  it('renders the AI settings error inline while keeping the panel usable', () => {
    render(
      <AISuggestionPanel
        suggestions={[]}
        aiError="aiSettingsMissing"
        aiLoading={false}
        applyAllLoading={false}
        applyId={null}
        isFull={false}
        rows={4}
        cols={5}
        refinePrompt=""
        selectedPosition={null}
        onApplyAll={vi.fn()}
        onRefresh={vi.fn()}
        onRefine={vi.fn()}
        onRegenerate={vi.fn()}
        onRefinePromptChange={vi.fn()}
        onApply={vi.fn()}
      />,
    );

    expect(screen.getByText('aiSettingsMissing')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'refresh' })).toBeInTheDocument();
  });
});
