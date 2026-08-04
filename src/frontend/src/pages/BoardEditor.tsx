import { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import { useBoardStore } from '../store/boardStore';
import { SymbolPicker } from '../components/board/SymbolPicker';
import { SymbolEditorDialog } from '../components/board/SymbolEditorDialog';
import { BoardEditorGrid } from '../components/board/BoardEditorGrid';
import type { BoardSymbol } from '../types';
import { useAuthStore } from '../store/authStore';
import { useSettingsStore } from '../store/settingsStore';
import { useToastStore } from '../store/toastStore';
import { useTranslation } from 'react-i18next';
import { AISuggestionPanel } from '../components/board/AISuggestionPanel';
import { BoardSettingsDialog } from '../components/board/BoardSettingsDialog';
import { BoardEditorToolbar } from '../components/board/BoardEditorToolbar';
import { useBoardAISuggestions } from '../hooks/useBoardAISuggestions';
import { useBoardCollab } from '../hooks/useBoardCollab';
import { useBoardEditorSymbols } from '../hooks/useBoardEditorSymbols';
import { getBoardPlayabilityStatus } from './boardEditorUtils';

export function BoardEditor() {
  const { t } = useTranslation('boards');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentBoard, fetchBoard, isLoading, error, addSymbolToBoard, batchUpdateSymbols, updateBoard, deleteBoardSymbol } = useBoardStore();
  const { user, token } = useAuthStore();
  const { aiSettings, fetchAISettings } = useSettingsStore();
  const { addToast } = useToastStore();
  const [isSymbolPickerOpen, setIsSymbolPickerOpen] = useState(false);
  const [selectedPosition, setSelectedPosition] = useState<{ x: number; y: number } | null>(null);
  const [gridPreset, setGridPreset] = useState<string>('4x5');

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [boardName, setBoardName] = useState('');
  const [boardDescription, setBoardDescription] = useState('');
  const [boardCategory, setBoardCategory] = useState('general');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiConfigError, setAiConfigError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [clearLoading, setClearLoading] = useState(false);

  const primaryProvider = aiSettings?.provider;
  const primaryModel = primaryProvider === 'openrouter'
    ? aiSettings?.openrouter_model
    : primaryProvider === 'lmstudio'
      ? aiSettings?.lmstudio_model
      : aiSettings?.ollama_model;
  const primaryReady = Boolean(primaryProvider && primaryModel);
  const resolvedProvider = primaryProvider;
  const resolvedModel = primaryModel;

  useEffect(() => {
    if (id) {
      fetchBoard(parseInt(id));
    }
  }, [id, fetchBoard]);

  useEffect(() => {
    if (!aiSettings) {
      fetchAISettings().catch(() => { });
    }
  }, [aiSettings, fetchAISettings]);

  useEffect(() => {
    if (currentBoard) {
      const r = currentBoard.grid_rows ?? 4
      const c = currentBoard.grid_cols ?? 5
      setGridPreset(`${r}x${c}`)

      setBoardName(currentBoard.name);
      setBoardDescription(currentBoard.description || '');
      setBoardCategory(currentBoard.category || 'general');
      setAiEnabled(currentBoard.ai_enabled || false);
    }
  }, [currentBoard]);

  const currentBoardId = currentBoard?.id;
  const {
    localSymbols,
    activeSymbol,
    editingSymbol,
    hasChanges,
    setHasChanges,
    setEditingSymbol,
    clearOverrides,
    handleRemoteMove,
    handleDragStart: handleSymbolDragStart,
    handleDragEnd: handleSymbolDragEnd,
    handleUpdateSymbol,
  } = useBoardEditorSymbols({ currentBoard });
  const status = useMemo(
    () => currentBoard
      ? getBoardPlayabilityStatus(currentBoard, localSymbols)
      : { playable: false, progress: 0, needed: 0, count: 0, threshold: 0 },
    [currentBoard, localSymbols],
  );

  const { sendMove } = useBoardCollab({
    boardId: currentBoardId,
    token,
    onRemoteMove: handleRemoteMove,
  });
  const {
    aiSuggestions,
    aiLoading,
    aiError,
    applyId,
    refinePrompt,
    applyAllLoading,
    setAiError,
    setRefinePrompt,
    loadAISuggestions,
    handleRefine,
    handleRegenerate,
    applySuggestion,
    applyAllSuggestions,
  } = useBoardAISuggestions({
    currentBoard,
    localSymbols,
    resolvedProvider,
    resolvedModel,
    fetchBoard,
    deleteBoardSymbol,
    setHasChanges,
  });

  useEffect(() => {
    if (!aiEnabled) {
      setAiConfigError(null);
      return;
    }
    if (!primaryReady) {
      setAiConfigError(t('aiSettingsMissing'));
      return;
    }
    setAiConfigError(null);
  }, [aiEnabled, primaryReady, t]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    handleSymbolDragStart(event.active.data.current as BoardSymbol);
  }, [handleSymbolDragStart]);

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    const symbolId = active.data.current?.id;
    const position = over?.data.current as { x: number; y: number } | undefined;
    handleSymbolDragEnd(symbolId, over && active.id !== over.id ? position : undefined, sendMove);
  }, [handleSymbolDragEnd, sendMove]);

  const handleAddSymbolClick = useCallback((x: number, y: number) => {
    setSelectedPosition({ x, y });
    setIsSymbolPickerOpen(true);
  }, []);

  const handleSymbolSelect = useCallback(async (symbolId: number) => {
    if (!currentBoard || !selectedPosition) return;

    try {
      const existing = localSymbols.find(s => s.position_x === selectedPosition.x && s.position_y === selectedPosition.y);
      if (existing) {
        await deleteBoardSymbol(currentBoard.id, existing.id);
      }
      await addSymbolToBoard(currentBoard.id, symbolId, selectedPosition);
      await fetchBoard(parseInt(id!), true);
      setHasChanges(true);
    } catch (error) {
      console.error('Failed to add symbol:', error);
      // Optional: Show user feedback if needed
    }
  }, [currentBoard, selectedPosition, addSymbolToBoard, fetchBoard, id, deleteBoardSymbol, localSymbols, setHasChanges]);

  const handleSave = useCallback(async () => {
    if (!currentBoard || !hasChanges) return;

    try {
      const updates = localSymbols.map(s => ({
        id: s.id,
        position_x: s.position_x,
        position_y: s.position_y,
        size: s.size,
        is_visible: s.is_visible,
        custom_text: s.custom_text,
        color: s.color,
        linked_board_id: s.linked_board_id ?? null
      }));

      await batchUpdateSymbols(currentBoard.id, updates);
      clearOverrides();
      setHasChanges(false);
      addToast(t('layoutSaved'), 'success');
    } catch (error) {
      console.error('Failed to save layout:', error);
      addToast(t('layoutSaveFailed'), 'error');
    }
  }, [currentBoard, hasChanges, localSymbols, batchUpdateSymbols, clearOverrides, setHasChanges, t, addToast]);

  const handleGridChange = useCallback(async (preset: string) => {
    setGridPreset(preset)
    const [r, c] = preset.split('x').map(Number)
    if (currentBoard) {
      try {
        await updateBoard(currentBoard.id, { grid_rows: r, grid_cols: c })
      } catch (e) {
        console.error('Failed to update grid layout', e)
      }
    }
  }, [currentBoard, updateBoard]);

  const handleSaveSettings = async () => {
    if (!currentBoard) return;
    if (aiEnabled && (!resolvedProvider || !resolvedModel)) {
      setAiConfigError(t('aiConfigIncomplete'));
      return;
    }

    try {
      await updateBoard(currentBoard.id, {
        name: boardName,
        description: boardDescription,
        category: boardCategory,
        ai_enabled: aiEnabled,
        ai_provider: aiEnabled ? (resolvedProvider ?? undefined) : undefined,
        ai_model: aiEnabled ? '@primary' : undefined
      });

      setSaveSuccess(true);
      setTimeout(() => {
        setSaveSuccess(false);
        setIsSettingsOpen(false);
      }, 1500);

      await fetchBoard(parseInt(id!), true);
      setHasChanges(true);
    } catch (error) {
      console.error('Failed to save board settings:', error);
      addToast(t('settingsSaveFailed'), 'error');
    }
  };

  const removeSymbol = useCallback(async (boardSymbolId: number) => {
    if (!currentBoard) return;
    try {
      await deleteBoardSymbol(currentBoard.id, boardSymbolId);
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setAiError(err?.response?.data?.detail || t('failedToRemoveSymbol'));
    }
  }, [currentBoard, deleteBoardSymbol, fetchBoard, setAiError, setHasChanges, t]);

  const clearBoard = useCallback(async () => {
    if (!currentBoard || !currentBoard.symbols?.length) return;
    setClearLoading(true);
    setAiError(null);
    try {
      for (const s of currentBoard.symbols) {
        await deleteBoardSymbol(currentBoard.id, s.id);
      }
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setAiError(err?.response?.data?.detail || t('failedToClearBoard'));
    } finally {
      setClearLoading(false);
    }
  }, [currentBoard, deleteBoardSymbol, fetchBoard, setAiError, setHasChanges, t]);

  if (isLoading && !currentBoard) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error && !currentBoard) {
    return (
      <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-4 rounded-lg">
        {error}
      </div>
    );
  }

  if (!currentBoard) {
    return <div className="text-gray-900 dark:text-gray-100">{t('boardNotFound')}</div>;
  }

  const rows = currentBoard.grid_rows ?? 4;
  const cols = currentBoard.grid_cols ?? 5;
  const boardCapacity = rows * cols;
  const filledCount = Math.max(localSymbols.length, currentBoard.symbols?.length ?? 0);
  const isFull = filledCount >= boardCapacity;

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col">
      <BoardEditorToolbar
        boardName={currentBoard.name}
        showSuggestions={Boolean(currentBoard.ai_enabled && (user?.id === currentBoard.user_id || user?.user_type === 'admin'))}
        aiLoading={aiLoading}
        status={status}
        gridPreset={gridPreset}
        hasChanges={hasChanges}
        hasSymbols={Boolean(currentBoard.symbols?.length)}
        isBusy={applyAllLoading || clearLoading}
        onLoadSuggestions={() => void loadAISuggestions()}
        onSpeakMode={() => navigate(`/play/${currentBoard.id}`)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onGridChange={handleGridChange}
        onSave={handleSave}
        onClear={clearBoard}
      />

      {currentBoard.ai_enabled && (aiSuggestions.length > 0 || aiError) && (
        <AISuggestionPanel
          suggestions={aiSuggestions}
          aiError={aiError}
          aiLoading={aiLoading}
          applyAllLoading={applyAllLoading || clearLoading}
          applyId={applyId}
          isFull={isFull}
          rows={rows}
          cols={cols}
          refinePrompt={refinePrompt}
          selectedPosition={selectedPosition}
          onApplyAll={applyAllSuggestions}
          onRefresh={() => loadAISuggestions()}
          onRefine={handleRefine}
          onRegenerate={handleRegenerate}
          onRefinePromptChange={setRefinePrompt}
          onApply={applySuggestion}
        />
      )}

      <BoardEditorGrid
        rows={rows}
        cols={cols}
        symbols={localSymbols}
        activeSymbol={activeSymbol}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onAddSymbol={handleAddSymbolClick}
        onRemoveSymbol={removeSymbol}
        onEditSymbol={setEditingSymbol}
      />

      <SymbolPicker
        isOpen={isSymbolPickerOpen}
        onClose={() => setIsSymbolPickerOpen(false)}
        onSelect={handleSymbolSelect}
        position={selectedPosition || { x: 0, y: 0 }}
      />

      <SymbolEditorDialog
        key={editingSymbol?.id}
        isOpen={!!editingSymbol}
        onClose={() => setEditingSymbol(null)}
        onSave={handleUpdateSymbol}
        symbol={editingSymbol}
      />

      <BoardSettingsDialog
        isOpen={isSettingsOpen}
        saveSuccess={saveSuccess}
        boardName={boardName}
        boardDescription={boardDescription}
        boardCategory={boardCategory}
        aiEnabled={aiEnabled}
        primaryReady={primaryReady}
        primaryProvider={primaryProvider}
        primaryModel={primaryModel}
        aiConfigError={aiConfigError}
        onClose={() => setIsSettingsOpen(false)}
        onSave={handleSaveSettings}
        onBoardNameChange={setBoardName}
        onBoardDescriptionChange={setBoardDescription}
        onBoardCategoryChange={setBoardCategory}
        onAiEnabledChange={setAiEnabled}
      />
    </div>
  );
}
