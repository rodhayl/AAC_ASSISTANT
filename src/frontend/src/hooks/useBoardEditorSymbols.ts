import { useCallback, useMemo, useState } from 'react';
import type { Board, BoardSymbol } from '../types';
import type { BoardPosition } from './useBoardCollab';
import { mergeBoardSymbols, type BoardSymbolOverrides } from '../pages/boardEditorUtils';

interface UseBoardEditorSymbolsOptions {
  currentBoard: Board | null;
  userId?: number | null;
}

export function useBoardEditorSymbols({ currentBoard, userId }: UseBoardEditorSymbolsOptions) {
  const [symbolOverridesByContext, setSymbolOverridesByContext] = useState<Record<string, BoardSymbolOverrides>>({});
  const [activeSymbolByContext, setActiveSymbolByContext] = useState<Record<string, BoardSymbol | null>>({});
  const [editingSymbolByContext, setEditingSymbolByContext] = useState<Record<string, BoardSymbol | null>>({});
  const [hasChangesByContext, setHasChangesByContext] = useState<Record<string, boolean>>({});
  const contextKey = currentBoard ? `${userId ?? 'anonymous'}:${currentBoard.id}` : null;
  const activeSymbol = contextKey ? activeSymbolByContext[contextKey] ?? null : null;
  const editingSymbol = contextKey ? editingSymbolByContext[contextKey] ?? null : null;
  const hasChanges = contextKey !== null && Boolean(hasChangesByContext[contextKey]);
  const symbolOverrides = contextKey ? symbolOverridesByContext[contextKey] : undefined;

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

  const handleRemoteMove = useCallback((symbolId: number, position: BoardPosition) => {
    updateSymbolOverride(symbolId, { position_x: position.x, position_y: position.y });
  }, [updateSymbolOverride]);

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
    setHasChanges(false);
  }, [contextKey, setHasChanges]);

  return {
    localSymbols,
    activeSymbol,
    editingSymbol,
    hasChanges,
    setHasChanges,
    setEditingSymbol,
    clearOverrides,
    handleRemoteMove,
    handleDragStart,
    handleDragEnd,
    handleUpdateSymbol,
  };
}
