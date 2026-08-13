import { useCallback, useMemo, useState } from 'react';
import type { Board, BoardSymbol } from '../types';
import type { BoardPosition } from './useBoardCollab';
import { mergeBoardSymbols, type BoardSymbolOverrides } from '../pages/boardEditorUtils';

interface UseBoardEditorSymbolsOptions {
  currentBoard: Board | null;
}

export function useBoardEditorSymbols({ currentBoard }: UseBoardEditorSymbolsOptions) {
  const [symbolOverridesByBoard, setSymbolOverridesByBoard] = useState<Record<number, BoardSymbolOverrides>>({});
  const [activeSymbol, setActiveSymbol] = useState<BoardSymbol | null>(null);
  const [editingSymbol, setEditingSymbol] = useState<BoardSymbol | null>(null);
  const [hasChanges, setHasChanges] = useState(false);
  const symbolOverrides = currentBoard ? symbolOverridesByBoard[currentBoard.id] : undefined;

  const localSymbols = useMemo(
    () => currentBoard ? mergeBoardSymbols(currentBoard.symbols, symbolOverrides ?? {}) : [],
    [currentBoard, symbolOverrides],
  );

  const updateSymbolOverride = useCallback((symbolId: number, updates: Partial<BoardSymbol>) => {
    if (!currentBoard) return;
    setSymbolOverridesByBoard((previous) => ({
      ...previous,
      [currentBoard.id]: {
        ...(previous[currentBoard.id] ?? {}),
        [symbolId]: {
          ...(previous[currentBoard.id]?.[symbolId] ?? {}),
          ...updates,
        },
      },
    }));
  }, [currentBoard]);

  const handleRemoteMove = useCallback((symbolId: number, position: BoardPosition) => {
    updateSymbolOverride(symbolId, { position_x: position.x, position_y: position.y });
  }, [updateSymbolOverride]);

  const handleDragStart = useCallback((symbol: BoardSymbol) => {
    setActiveSymbol(symbol);
  }, []);

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
  }, [localSymbols, updateSymbolOverride]);

  const handleUpdateSymbol = useCallback((updates: Partial<BoardSymbol>) => {
    if (!editingSymbol) return;
    updateSymbolOverride(editingSymbol.id, updates);
    setHasChanges(true);
    setEditingSymbol(null);
  }, [editingSymbol, updateSymbolOverride]);

  const clearOverrides = useCallback(() => {
    if (!currentBoard) return;
    setSymbolOverridesByBoard((previous) => {
      const next = { ...previous };
      delete next[currentBoard.id];
      return next;
    });
  }, [currentBoard]);

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
