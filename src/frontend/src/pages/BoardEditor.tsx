import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router';
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
import { StatusMessage } from '../components/ui/StatusMessage';
import { useBoardAISuggestions } from '../hooks/useBoardAISuggestions';
import api, { extractError } from '../lib/api';
import { useBoardCollab } from '../hooks/useBoardCollab';
import { useBoardEditorSymbols } from '../hooks/useBoardEditorSymbols';
import { getBoardPlayabilityStatus } from './boardEditorUtils';
import { LoadingState } from '../components/ui/LoadingState';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';

export function BoardEditor() {
  const { t } = useTranslation('boards');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const currentBoard = useBoardStore((state) => state.currentBoard);
  const fetchBoard = useBoardStore((state) => state.fetchBoard);
  const isBoardLoading = useBoardStore((state) => state.isBoardLoading);
  const error = useBoardStore((state) => state.error);
  const addSymbolToBoard = useBoardStore((state) => state.addSymbolToBoard);
  const batchUpdateSymbols = useBoardStore((state) => state.batchUpdateSymbols);
  const updateBoard = useBoardStore((state) => state.updateBoard);
  const deleteBoardSymbol = useBoardStore((state) => state.deleteBoardSymbol);
  const user = useAuthStore((state) => state.user);
  const token = useAuthStore((state) => state.token);
  const aiSettings = useSettingsStore((state) => state.aiSettings);
  const fetchAISettings = useSettingsStore((state) => state.fetchAISettings);
  const addToast = useToastStore((state) => state.addToast);
  const [isSymbolPickerOpen, setIsSymbolPickerOpen] = useState(false);
  const [selectedPosition, setSelectedPosition] = useState<{ x: number; y: number } | null>(null);
  const [gridPreset, setGridPreset] = useState<string>('4x5');

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [boardName, setBoardName] = useState('');
  const [boardDescription, setBoardDescription] = useState('');
  const [boardCategory, setBoardCategory] = useState('general');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiConfigError, setAiConfigError] = useState<string | null>(null);  const [saveSuccess, setSaveSuccess] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)
  const [clearLoading, setClearLoading] = useState(false)
  const [clearDialogOpen, setClearDialogOpen] = useState(false)
  const saveSettingsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
;

  const primaryProvider = aiSettings?.provider;
  const primaryModel = primaryProvider === 'openrouter'
    ? aiSettings?.openrouter_model
    : primaryProvider === 'lmstudio'
      ? aiSettings?.lmstudio_model
      : primaryProvider === 'groq'
        ? aiSettings?.groq_model
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
    setHasChanges,
  });

  useEffect(() => {
    return () => {
      if (saveSettingsTimer.current !== null) {
        clearTimeout(saveSettingsTimer.current);
      }
    };
  }, []);

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
        // Replace in one server mutation. Deleting first could permanently lose
        // the old placement when the subsequent add failed.
        await api.put(`/boards/${currentBoard.id}/symbols/${existing.id}`, {
          symbol_id: symbolId,
          position_x: selectedPosition.x,
          position_y: selectedPosition.y,
        });
      } else {
        await addSymbolToBoard(currentBoard.id, symbolId, selectedPosition);
      }
      await fetchBoard(parseInt(id!), true);
      setHasChanges(true);
    } catch (error) {
      console.error('Failed to add symbol:', error);
      addToast(extractError(error, t('failedToAddSymbol')), 'error');
    }
  }, [currentBoard, selectedPosition, addSymbolToBoard, fetchBoard, id, localSymbols, setHasChanges, addToast, t]);

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
    const [r, c] = preset.split('x').map(Number)
    if (!currentBoard) return
    try {
      await updateBoard(currentBoard.id, { grid_rows: r, grid_cols: c })
      setGridPreset(preset)
    } catch (e) {
      console.error('Failed to update grid layout', e)
      setGridPreset(`${currentBoard.grid_rows ?? 4}x${currentBoard.grid_cols ?? 5}`)
      addToast(t('settingsSaveFailed'), 'error')
    }
  }, [addToast, currentBoard, t, updateBoard]);

  const handleSaveSettings = async () => {
    if (!currentBoard) return;
    const trimmedBoardName = boardName.trim();
    if (!trimmedBoardName) {
      addToast(t('boardNameRequired'), 'error');
      return;
    }
    if (aiEnabled && (!resolvedProvider || !resolvedModel)) {
      setAiConfigError(t('aiConfigIncomplete'));
      return;
    }

    setSavingSettings(true);
    try {
      await updateBoard(currentBoard.id, {
        name: trimmedBoardName,
        description: boardDescription,
        category: boardCategory,
        ai_enabled: aiEnabled,
        ai_provider: aiEnabled ? (resolvedProvider ?? undefined) : null,
        ai_model: aiEnabled ? '@primary' : null
      });

      setSaveSuccess(true);
      if (saveSettingsTimer.current !== null) {
        clearTimeout(saveSettingsTimer.current);
      }
      saveSettingsTimer.current = setTimeout(() => {
        saveSettingsTimer.current = null;
        setSaveSuccess(false);
        setIsSettingsOpen(false);
      }, 1500);

      await fetchBoard(parseInt(id!), true);
    } catch (error) {
      console.error('Failed to save board settings:', error);
      addToast(t('settingsSaveFailed'), 'error');
    } finally {
      setSavingSettings(false);
    }
  };

  const removeSymbol = useCallback(async (boardSymbolId: number) => {
    if (!currentBoard) return;
    try {
      await deleteBoardSymbol(currentBoard.id, boardSymbolId);
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
    } catch (e: unknown) {
      // Toast (not the AI panel error) so the failure is visible even on
      // boards without AI enabled, where the panel never renders.
      addToast(extractError(e, t('failedToRemoveSymbol')), 'error');
    }
  }, [currentBoard, deleteBoardSymbol, fetchBoard, setHasChanges, t, addToast]);

  const clearBoard = useCallback(async () => {
    if (!currentBoard || !currentBoard.symbols?.length) return;
    setClearLoading(true);
    try {
      for (const s of currentBoard.symbols) {
        await deleteBoardSymbol(currentBoard.id, s.id);
      }
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
      setClearDialogOpen(false);
    } catch (e: unknown) {
      // Toast (not the AI panel error) so the failure is visible even on
      // boards without AI enabled, where the panel never renders.
      addToast(extractError(e, t('failedToClearBoard')), 'error');
    } finally {
      setClearLoading(false);
    }
  }, [currentBoard, deleteBoardSymbol, fetchBoard, setHasChanges, t, addToast]);

  const requestClearBoard = useCallback(() => {
    setClearDialogOpen(true);
  }, []);

  if (isBoardLoading && !currentBoard) {
    return (
      <LoadingState label={t('loadingBoard')} />
    );
  }

  if (error && !currentBoard) {
    return (
      <StatusMessage variant="error">
        {error}
      </StatusMessage>
    );
  }

  if (!currentBoard) {
    return <div className="text-foreground">{t('boardNotFound')}</div>;
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
        onClear={requestClearBoard}
      />

      <ConfirmDialog
        isOpen={clearDialogOpen}
        onClose={() => setClearDialogOpen(false)}
        onConfirm={() => void clearBoard()}
        title={t('clearBoardTitle')}
        description={t('clearBoardConfirm')}
        confirmText={t('clearBoard')}
        cancelText={t('cancel')}
        variant="danger"
        isLoading={clearLoading}
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
        currentBoardId={currentBoard.id}
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
        saving={savingSettings}
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
