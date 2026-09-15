import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Board, BoardSymbol } from '../types';
import type { BoardPosition } from './useBoardCollab';
import { mergeBoardSymbols, type BoardSymbolOverrides } from '../pages/boardEditorUtils';

interface UseBoardEditorSymbolsOptions {
  currentBoard: Board | null;
  userId?: number | null;
}

/**
 * How many `${userId}:${boardId}` contexts keep their pending state. The maps
 * below were append-only for the whole session (one entry per visited board and
 * collaborator) (G1); the cap keeps the most recently used contexts so
 * navigating back to the board you just edited still recovers its local edit.
 */
export const MAX_EDITOR_CONTEXTS = 5;

/** Drop anything beyond the retained keys (most recent last). */
function keepRetained<T>(previous: Record<string, T>, retained: string[]): Record<string, T> {
  const next: Record<string, T> = {};
  for (const key of retained) {
    if (key in previous) next[key] = previous[key];
  }
  return next;
}

export function useBoardEditorSymbols({ currentBoard, userId }: UseBoardEditorSymbolsOptions) {
  const [symbolOverridesByContext, setSymbolOverridesByContext] = useState<Record<string, BoardSymbolOverrides>>({});
  const [activeSymbolByContext, setActiveSymbolByContext] = useState<Record<string, BoardSymbol | null>>({});
  const [editingSymbolByContext, setEditingSymbolByContext] = useState<Record<string, BoardSymbol | null>>({});
  const [hasChangesByContext, setHasChangesByContext] = useState<Record<string, boolean>>({});
  // Placement ids whose current position came from a collaborator, not from
  // this user's own edit (A17). They render like any override, but they must
  // never enable Save on their own.
  const [remoteMovedByContext, setRemoteMovedByContext] = useState<Record<string, number[]>>({});
  const contextKey = currentBoard ? `${userId ?? 'anonymous'}:${currentBoard.id}` : null;
  const activeSymbol = contextKey ? activeSymbolByContext[contextKey] ?? null : null;
  const editingSymbol = contextKey ? editingSymbolByContext[contextKey] ?? null : null;
  const hasChanges = contextKey !== null && Boolean(hasChangesByContext[contextKey]);
  const symbolOverrides = contextKey ? symbolOverridesByContext[contextKey] : undefined;
  const remoteMovedIds = useMemo(
    () => (contextKey ? remoteMovedByContext[contextKey] ?? [] : []),
    [contextKey, remoteMovedByContext],
  );

  // Bounded most-recently-used context list; trimmed on every context switch.
  const contextOrderRef = useRef<string[]>([]);
  useEffect(() => {
    if (contextKey === null) return;
    const order = [...contextOrderRef.current.filter((key) => key !== contextKey), contextKey];
    const retained = order.slice(-MAX_EDITOR_CONTEXTS);
    contextOrderRef.current = retained;
    if (retained.length === order.length && order.length > 1) return;
    setSymbolOverridesByContext((previous) => keepRetained(previous, retained));
    setActiveSymbolByContext((previous) => keepRetained(previous, retained));
    setEditingSymbolByContext((previous) => keepRetained(previous, retained));
    setHasChangesByContext((previous) => keepRetained(previous, retained));
    setRemoteMovedByContext((previous) => keepRetained(previous, retained));
  }, [contextKey]);

  const setActiveSymbol = useCallback((symbol: BoardSymbol | null) => {
    if (!contextKey) return;
    setActiveSymbolByContext((previous) => ({ ...previous, [contextKey]: symbol }));
  }, [contextKey]);

  const setEditingSymbol = useCallback((symbol: BoardSymbol | null) => {
    if (!contextKey) return;
    setEditingSymbolByContext((previous) => ({ ...previous, [contextKey]: symbol }));
  }, [contextKey]);

  const setHasChanges = useCallback((value: boolean) => {
    if (contextKey === null) return;
    setHasChangesByContext((previous) => {
      if (value === Boolean(previous[contextKey])) return previous;
      const next = { ...previous };
      if (value) next[contextKey] = true;
      else delete next[contextKey];
      return next;
    });
  }, [contextKey]);

  const localSymbols = useMemo(
    () => currentBoard ? mergeBoardSymbols(currentBoard.symbols, symbolOverrides ?? {}) : [],
    [currentBoard, symbolOverrides],
  );

  const updateSymbolOverride = useCallback((symbolId: number, updates: Partial<BoardSymbol>) => {
    if (!contextKey) return;
    setSymbolOverridesByContext((previous) => ({
      ...previous,
      [contextKey]: {
        ...(previous[contextKey] ?? {}),
        [symbolId]: {
          ...(previous[contextKey]?.[symbolId] ?? {}),
          ...updates,
        },
      },
    }));
  }, [contextKey]);

  const markRemotelyMoved = useCallback((symbolId: number) => {
    if (!contextKey) return;
    setRemoteMovedByContext((previous) => {
      const current = previous[contextKey] ?? [];
      if (current.includes(symbolId)) return previous;
      return { ...previous, [contextKey]: [...current, symbolId] };
    });
  }, [contextKey]);

  const handleRemoteMove = useCallback((symbolId: number, position: BoardPosition) => {
    // Show the collaborator's position without claiming it as local dirt: Save
    // stays disabled, and a save triggered by a later local edit still carries
    // both placements (localSymbols is what the save loop serializes) (A17).
    updateSymbolOverride(symbolId, { position_x: position.x, position_y: position.y });
    markRemotelyMoved(symbolId);
  }, [updateSymbolOverride, markRemotelyMoved]);

  const handleDragStart = useCallback((symbol: BoardSymbol) => {
    setActiveSymbol(symbol);
  }, [setActiveSymbol]);

  const handleDragEnd = useCallback((
    symbolId: number | undefined,
    position: BoardPosition | undefined,
    sendMove: (symbolId: number, position: BoardPosition) => void,
  ) => {
    if (symbolId == null || !position) {
      setActiveSymbol(null);
      return;
    }

    const occupied = localSymbols.find(
      (symbol) =>
        symbol.position_x === position.x &&
        symbol.position_y === position.y &&
        symbol.id !== symbolId,
    );
    if (!occupied) {
      updateSymbolOverride(symbolId, {
        position_x: position.x,
        position_y: position.y,
      });
      setHasChanges(true);
      sendMove(symbolId, position);
    }
    setActiveSymbol(null);
  }, [localSymbols, setActiveSymbol, setHasChanges, updateSymbolOverride]);

  const handleUpdateSymbol = useCallback((updates: Partial<BoardSymbol>) => {
    if (!editingSymbol) return;
    updateSymbolOverride(editingSymbol.id, updates);
    setHasChanges(true);
    setEditingSymbol(null);
  }, [editingSymbol, setEditingSymbol, setHasChanges, updateSymbolOverride]);

  const clearOverrides = useCallback(() => {
    if (!contextKey) return;
    setSymbolOverridesByContext((previous) => {
      const next = { ...previous };
      delete next[contextKey];
      return next;
    });
    setRemoteMovedByContext((previous) => {
      const next = { ...previous };
      delete next[contextKey];
      return next;
    });
    setHasChanges(false);
  }, [contextKey, setHasChanges]);

  return {
    localSymbols,
    activeSymbol,
    editingSymbol,
    hasChanges,
    remoteMovedIds,
    setHasChanges,
    setEditingSymbol,
    clearOverrides,
    handleRemoteMove,
    handleDragStart,
    handleDragEnd,
    handleUpdateSymbol,
  };
}
