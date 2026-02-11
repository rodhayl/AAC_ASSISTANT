import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  DndContext,
  DragOverlay,
  useSensor,
  useSensors,
  PointerSensor
} from '@dnd-kit/core';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import { useBoardStore } from '../store/boardStore';
import { DraggableSymbol } from '../components/board/DraggableSymbol';
import { DroppableCell } from '../components/board/DroppableCell';
import { SymbolPicker } from '../components/board/SymbolPicker';
import { SymbolEditorDialog } from '../components/board/SymbolEditorDialog';
import type { BoardSymbol } from '../types';
import { useAuthStore } from '../store/authStore';
import { useSettingsStore } from '../store/settingsStore';
import { useToastStore } from '../store/toastStore';
import { Save, Settings, Sparkles, PlusCircle, RefreshCcw, Trash2, ArrowLeftRight, Play, Lock, Unlock } from 'lucide-react';
import { createWSClient } from '../lib/ws';
import { config } from '../config';
import { useTranslation } from 'react-i18next';

type AISuggestion = {
  label: string;
  symbol_key?: string;
  color?: string;
  description?: string;
};

export function BoardEditor() {
  const { t } = useTranslation('boards');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentBoard, fetchBoard, isLoading, error, addSymbolToBoard, batchUpdateSymbols, updateBoard, deleteBoardSymbol } = useBoardStore();
  const { user, token } = useAuthStore();
  const { aiSettings, fallbackAISettings, fetchAISettings, fetchFallbackAISettings } = useSettingsStore();
  const { addToast } = useToastStore();
  const [activeSymbol, setActiveSymbol] = useState<BoardSymbol | null>(null);
  const [isSymbolPickerOpen, setIsSymbolPickerOpen] = useState(false);
  const [editingSymbol, setEditingSymbol] = useState<BoardSymbol | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<{ x: number; y: number } | null>(null);
  const [gridPreset, setGridPreset] = useState<string>('4x5');

  const [localSymbols, setLocalSymbols] = useState<BoardSymbol[]>([]);
  const [hasChanges, setHasChanges] = useState(false);
  const [wsClient, setWsClient] = useState<ReturnType<typeof createWSClient> | null>(null)

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [boardName, setBoardName] = useState('');
  const [boardDescription, setBoardDescription] = useState('');
  const [boardCategory, setBoardCategory] = useState('general');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiSource, setAiSource] = useState<'primary' | 'fallback'>('primary');
  const [aiConfigError, setAiConfigError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [applyId, setApplyId] = useState<string | null>(null);
  const [refinePrompt, setRefinePrompt] = useState('');
  const [applyAllLoading, setApplyAllLoading] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  const primaryProvider = aiSettings?.provider;
  const primaryModel = primaryProvider === 'openrouter' ? aiSettings?.openrouter_model : aiSettings?.ollama_model;
  const fallbackProvider = fallbackAISettings?.provider;
  const fallbackModel = fallbackProvider === 'openrouter' ? fallbackAISettings?.openrouter_model : fallbackAISettings?.ollama_model;
  const primaryReady = Boolean(primaryProvider && primaryModel);
  const fallbackReady = Boolean(fallbackProvider && fallbackModel);
  const selectedSettings = aiSource === 'fallback' ? fallbackAISettings : aiSettings;
  const resolvedProvider = selectedSettings?.provider;
  const resolvedModel = resolvedProvider === 'openrouter' ? selectedSettings?.openrouter_model : selectedSettings?.ollama_model;

  useEffect(() => {
    if (id) {
      fetchBoard(parseInt(id));
    }
  }, [id, fetchBoard]);

  useEffect(() => {
    if (!aiSettings) {
      fetchAISettings().catch(() => { });
    }
    if (!fallbackAISettings) {
      fetchFallbackAISettings().catch(() => { });
    }
  }, [aiSettings, fallbackAISettings, fetchAISettings, fetchFallbackAISettings]);

  useEffect(() => {
    if (currentBoard) {
      setTimeout(() => setLocalSymbols(currentBoard.symbols), 0);
    }
  }, [currentBoard]);

  const status = useCallback(() => {
    if (!currentBoard) return { playable: false, progress: 0, needed: 0, count: 0, threshold: 0 };
    const capacity = (currentBoard.grid_rows ?? 4) * (currentBoard.grid_cols ?? 5);
    const threshold = Math.ceil(capacity * 0.5);

    const playableSymbolsCount = localSymbols.filter(s =>
      s.is_visible && (s.custom_text || s.symbol?.label)
    ).length;

    const progress = Math.round((playableSymbolsCount / threshold) * 100);
    const needed = Math.max(0, threshold - playableSymbolsCount);

    return {
      playable: playableSymbolsCount >= threshold,
      progress,
      needed,
      count: playableSymbolsCount,
      threshold
    };
  }, [currentBoard, localSymbols])();

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
  }, [currentBoard, resolvedModel, resolvedProvider]);

  const currentBoardId = currentBoard?.id

  useEffect(() => {
    if (!currentBoardId || !token) return
    const url = `${config.WS_BASE_URL}/collab/boards/${currentBoardId}?token=${encodeURIComponent(token)}`
    const client = createWSClient(url, {
      onMessage: (msg) => {
        const wsMsg = msg as { type?: string; payload?: { op: string; symbol_id?: number; position?: { x: number; y: number } } } | null
        if (wsMsg?.type === 'board_change' && wsMsg?.payload) {
          const p = wsMsg.payload
          if (p.op === 'move' && p.symbol_id != null && p.position) {
            const pos = p.position
            setLocalSymbols(prev => prev.map(s => s.id === p.symbol_id ? { ...s, position_x: pos.x, position_y: pos.y } : s))
          }
        }
      }
    })
    setWsClient(client)
    return () => {
      client.close()
    }
  }, [currentBoardId, token])

  useEffect(() => {
    if (!currentBoard) return;
    const boardProvider = currentBoard.ai_provider;
    const boardModel = currentBoard.ai_model;

    // Explicit markers for global settings
    if (boardModel === '@primary') {
      setAiSource('primary');
      return;
    }
    if (boardModel === '@fallback') {
      setAiSource('fallback');
      return;
    }

    // Default to primary; switch to fallback if it matches configured fallback settings
    if (boardProvider && fallbackProvider && boardProvider === fallbackProvider) {
      if (!boardModel || boardModel === fallbackModel) {
        setAiSource('fallback');
        return;
      }
    }
    setAiSource('primary');
  }, [currentBoard, fallbackModel, fallbackProvider]);

  useEffect(() => {
    if (!aiEnabled) {
      setAiConfigError(null);
      return;
    }
    if (!primaryReady) {
      setAiConfigError(t('aiSettingsMissing'));
      return;
    }
    if (aiSource === 'fallback' && !fallbackReady) {
      setAiConfigError(t('fallbackAINotConfigured'));
      return;
    }
    setAiConfigError(null);
  }, [aiEnabled, aiSource, primaryReady, fallbackReady, t]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const symbol = event.active.data.current as BoardSymbol;
    setActiveSymbol(symbol);
  }, []);

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const symbolId = active.data.current?.id;
      const { x, y } = over.data.current as { x: number, y: number };

      const occupied = localSymbols.find(s => s.position_x === x && s.position_y === y && s.id !== symbolId);

      if (!occupied) {
        setLocalSymbols(prev => prev.map(s => {
          if (s.id === symbolId) {
            return { ...s, position_x: x, position_y: y };
          }
          return s;
        }));
        setHasChanges(true);
        if (wsClient) {
          wsClient.send({ op: 'move', symbol_id: symbolId, position: { x, y } })
        }
      }
    }

    setActiveSymbol(null);
  }, [localSymbols, wsClient]);

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
  }, [currentBoard, selectedPosition, addSymbolToBoard, fetchBoard, id, deleteBoardSymbol, localSymbols]);

  const handleEditSymbol = useCallback((symbol: BoardSymbol) => {
    setEditingSymbol(symbol);
  }, []);

  const handleUpdateSymbol = useCallback((updates: Partial<BoardSymbol>) => {
    if (!editingSymbol) return;

    setLocalSymbols(prev => prev.map(s =>
      s.id === editingSymbol.id ? { ...s, ...updates } : s
    ));
    setHasChanges(true);
    setEditingSymbol(null);
  }, [editingSymbol]);

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
      setHasChanges(false);
      addToast(t('layoutSaved'), 'success');
    } catch (error) {
      console.error('Failed to save layout:', error);
      addToast(t('layoutSaveFailed'), 'error');
    }
  }, [currentBoard, hasChanges, localSymbols, batchUpdateSymbols, t, addToast]);

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
        ai_model: aiEnabled ? (aiSource === 'fallback' ? '@fallback' : '@primary') : undefined
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

  const loadAISuggestions = useCallback(async (options?: { refinePrompt?: string; regenerate?: boolean }) => {
    if (!currentBoard?.ai_enabled) return;
    if (!resolvedProvider || !resolvedModel) {
      setAiError(t('aiSettingsMissing'));
      return;
    }
    setAiLoading(true);
    setAiError(null);
    try {
      const api = (await import('../lib/api')).default;
      const body: Record<string, unknown> = {
        ai_source: aiSource
      };
      if (options?.refinePrompt) body.refine_prompt = options.refinePrompt;
      if (options?.regenerate) body.regenerate = true;
      const res = await api.post(`/boards/${currentBoard.id}/ai/suggestions`, body);
      const items: AISuggestion[] = res.data.items || [];
      setAiSuggestions(items);
      if (!items.length) {
        setAiError(t('noSuggestions'));
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setAiError(err?.response?.data?.detail || t('failedToLoadSuggestions'));
      setAiSuggestions([]);
    } finally {
      setAiLoading(false);
    }
  }, [currentBoard, resolvedModel, resolvedProvider, t, aiSource]);

  const handleRefine = useCallback(() => {
    const prompt = refinePrompt.trim();
    if (!prompt) {
      setAiError(t('refinePromptRequired'));
      return;
    }
    loadAISuggestions({ refinePrompt: prompt, regenerate: false });
  }, [loadAISuggestions, refinePrompt, t]);

  const handleRegenerate = useCallback(() => {
    const prompt = refinePrompt.trim();
    loadAISuggestions({ refinePrompt: prompt || undefined, regenerate: true });
  }, [loadAISuggestions, refinePrompt]);

  const applySuggestion = useCallback(async (item: AISuggestion, position?: { x: number; y: number }) => {
    if (!currentBoard) return;
    const capacity = (currentBoard.grid_rows ?? 4) * (currentBoard.grid_cols ?? 5);
    const filled = Math.max(localSymbols.length, currentBoard.symbols?.length ?? 0);
    if (!position && filled >= capacity) {
      setAiError(t('boardFull'));
      return;
    }
    setApplyId(item.label);
    try {
      const api = (await import('../lib/api')).default;
      if (position) {
        const existing = currentBoard.symbols?.find(s => s.position_x === position.x && s.position_y === position.y);
        if (existing) {
          await deleteBoardSymbol(currentBoard.id, existing.id);
        }
      }
      await api.post(`/boards/${currentBoard.id}/ai/suggestions/apply`, { item, position_x: position?.x, position_y: position?.y });
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setAiError(err?.response?.data?.detail || t('failedToAddSuggestion'));
    } finally {
      setApplyId(null);
    }
  }, [currentBoard, fetchBoard, deleteBoardSymbol, localSymbols, t]);

  const applyAllSuggestions = useCallback(async () => {
    if (!currentBoard || !aiSuggestions.length) return;
    const capacity = (currentBoard.grid_rows ?? 4) * (currentBoard.grid_cols ?? 5);
    const filled = Math.max(localSymbols.length, currentBoard.symbols?.length ?? 0);
    const remaining = capacity - filled;
    if (remaining <= 0) {
      setAiError(t('boardFull'));
      return;
    }
    setApplyAllLoading(true);
    setAiError(null);
    let successCount = 0;
    const failures: string[] = [];
    try {
      const api = (await import('../lib/api')).default;
      for (const item of aiSuggestions) {
        if (successCount >= remaining) {
          failures.push(t('boardFullSkipped'));
          break;
        }
        try {
          await api.post(`/boards/${currentBoard.id}/ai/suggestions/apply`, { item });
          successCount += 1;
        } catch (err: unknown) {
          const error = err as { response?: { data?: { detail?: string } }, message?: string };
          const detail = error?.response?.data?.detail || error?.message || 'unknown error';
          failures.push(`${item.label}: ${detail}`);
        }
      }
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setAiError(err?.response?.data?.detail || t('failedToAddAll'));
    } finally {
      if (failures.length) {
        setAiError(t('addSuggestionResult', { success: successCount, total: aiSuggestions.length, failures: failures.join('; ') }));
      }
      setApplyAllLoading(false);
    }
  }, [aiSuggestions, currentBoard, fetchBoard, localSymbols, t]);

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
  }, [currentBoard, deleteBoardSymbol, fetchBoard, t]);

  const clearBoard = useCallback(async () => {
    if (!currentBoard || !currentBoard.symbols?.length) return;
    setApplyAllLoading(true);
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
      setApplyAllLoading(false);
    }
  }, [currentBoard, deleteBoardSymbol, fetchBoard, t]);

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
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{currentBoard.name}</h1>
          <p className="text-gray-500 dark:text-gray-400">{t('editBoardSubtitle')}</p>
        </div>
        <div className="flex space-x-3 items-center">
          {/* Playability Status */}
          <div className={`hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full border ${status.playable
            ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400'
            : 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400'
            }`}>
            {status.playable ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
            <span className="text-xs font-bold uppercase tracking-wider">
              {status.playable
                ? t('boardReady', 'Board Ready')
                : t('boardIncomplete', '{{count}}/{{total}} Symbols', { count: status.count, total: status.threshold })}
            </span>
            {!status.playable && (
              <div className="w-24 h-2 bg-amber-200 dark:bg-amber-900/50 rounded-full overflow-hidden ml-2 border border-amber-300 dark:border-amber-800 shadow-inner">
                <div
                  className="h-full bg-gradient-to-r from-amber-400 to-amber-600 transition-all duration-700 ease-out shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                  style={{ width: `${status.progress}%` }}
                />
              </div>
            )}
          </div>

          {currentBoard.ai_enabled && (user?.id === currentBoard.user_id || user?.user_type === 'admin') && (
            <button
              onClick={() => loadAISuggestions()}
              disabled={aiLoading}
              className="inline-flex items-center px-4 py-2 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100 disabled:opacity-50"
            >
              <Sparkles className={`w-4 h-4 mr-2 ${aiLoading ? 'animate-spin' : ''}`} />
              {aiLoading ? t('fetchingIdeas') : t('getSuggestions')}
            </button>
          )}
          <button
            onClick={() => navigate(`/play/${currentBoard.id}`)}
            className="inline-flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 shadow-sm transition-colors"
            title={t('enterSpeakMode')}
          >
            <Play className="w-4 h-4 mr-2 fill-current" />
            {t('speakMode')}
          </button>
          <button
            onClick={() => setIsSettingsOpen(true)}
            className="p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            aria-label={t('boardSettings')}
          >
            <Settings className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <label htmlFor="board-layout" className="text-sm text-gray-600 dark:text-gray-400">{t('layout')}</label>
            <select
              id="board-layout"
              name="board_layout"
              value={gridPreset}
              onChange={(e) => handleGridChange(e.target.value)}
              className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="2x2">2x2</option>
              <option value="3x3">3x3</option>
              <option value="4x4">4x4</option>
              <option value="2x6">2x6</option>
              <option value="4x5">4x5</option>
            </select>
          </div>
          <button
            onClick={handleSave}
            disabled={!hasChanges}
            className={`flex items-center px-4 py-2 rounded-lg ${hasChanges
              ? 'bg-indigo-600 text-white hover:bg-indigo-700'
              : 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
              }`}
          >
            <Save className="w-4 h-4 mr-2" />
            {hasChanges ? t('saveLayout') : t('noChanges')}
          </button>
          <button
            onClick={clearBoard}
            disabled={applyAllLoading || !currentBoard.symbols?.length}
            className="flex items-center px-4 py-2 rounded-lg bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 disabled:opacity-50"
            title={t('clearBoardTitle')}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            {t('clearBoard')}
          </button>
        </div>
      </div>

      {currentBoard.ai_enabled && (aiSuggestions.length > 0 || aiError) && (
        <div className="bg-white dark:bg-gray-800 border border-indigo-100 dark:border-indigo-800 rounded-xl p-4 shadow-sm mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{t('aiSuggestionsTitle')}</h3>
            </div>
            <div className="flex gap-2">
              <button
                onClick={applyAllSuggestions}
                disabled={aiLoading || applyAllLoading || !aiSuggestions.length}
                className="flex items-center text-sm px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                title={t('addAllTitle')}
              >
                <PlusCircle className="w-4 h-4 mr-1" />
                {applyAllLoading ? t('addingAll') : t('addAll')}
              </button>
              <button
                onClick={() => loadAISuggestions()}
                className="flex items-center text-sm text-indigo-600 hover:text-indigo-700"
                disabled={aiLoading}
              >
                <RefreshCcw className={`w-4 h-4 mr-1 ${aiLoading ? 'animate-spin' : ''}`} />
                {t('refresh')}
              </button>
            </div>
          </div>
          {isFull && (
            <div className="mb-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              {t('boardFullWarning', { rows, cols })}
            </div>
          )}
          <div className="grid gap-2 mb-3 md:grid-cols-[1fr_auto_auto] md:items-center">
            <div className="md:col-span-1">
              <label className="block text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">
                {t('refineLabel')}
              </label>
              <input
                type="text"
                value={refinePrompt}
                onChange={(e) => setRefinePrompt(e.target.value)}
                placeholder={t('refinePlaceholder')}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900/40 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
            <button
              onClick={handleRefine}
              disabled={aiLoading}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-60"
            >
              {aiLoading ? t('refining') : t('sendRefinePrompt')}
            </button>
            <button
              onClick={handleRegenerate}
              disabled={aiLoading}
              className="px-4 py-2 bg-white dark:bg-gray-900/60 border border-indigo-200 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-800 disabled:opacity-60"
              title={t('regenerateTitle')}
            >
              {aiLoading ? t('regenerating') : t('regenerateFullBoard')}
            </button>
          </div>
          {aiError && <div className="text-sm text-red-600 mb-2">{aiError}</div>}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {aiSuggestions.map((item) => (
              <div key={item.label} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-900/40 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-gray-900 dark:text-gray-100">{item.label}</div>
                    {item.symbol_key && <div className="text-xs text-gray-500">{t('keyword', { key: item.symbol_key })}</div>}
                  </div>
                  {item.color && <span className="w-4 h-4 rounded-full border" style={{ background: item.color }} />}
                </div>
                {item.description && <div className="text-xs text-gray-500">{item.description}</div>}
                <button
                  onClick={() => applySuggestion(item)}
                  disabled={applyId === item.label}
                  className="inline-flex items-center justify-center px-3 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  <PlusCircle className="w-4 h-4 mr-1" />
                  {applyId === item.label ? t('adding') : t('addToBoard')}
                </button>
                <button
                  onClick={() => applySuggestion(item, selectedPosition || undefined)}
                  disabled={applyId === item.label || !selectedPosition}
                  className="inline-flex items-center justify-center px-3 py-2 text-sm bg-white dark:bg-gray-900/60 border border-indigo-200 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-800 disabled:opacity-50"
                  title={t('replaceTitle')}
                >
                  <ArrowLeftRight className="w-4 h-4 mr-1" />
                  {applyId === item.label ? t('replacing') : t('replaceAtSelected')}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-8 overflow-auto">
        <DndContext
          sensors={sensors}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <div
            className="grid gap-4 mx-auto max-w-4xl"
            style={{
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`
            }}
          >
            {Array.from({ length: rows }).map((_, row) => (
              Array.from({ length: cols }).map((_, col) => {
                const symbol = localSymbols.find(s => s.position_x === col && s.position_y === row);

                return (
                  <DroppableCell
                    key={`${col}-${row}`}
                    x={col}
                    y={row}
                    onAddClick={() => handleAddSymbolClick(col, row)}
                  >
                    {symbol && <DraggableSymbol boardSymbol={symbol} onRemove={removeSymbol} onEdit={handleEditSymbol} />}
                  </DroppableCell>
                );
              })
            ))}
          </div>

          <DragOverlay>
            {activeSymbol ? (
              <div className="w-32 h-32">
                <DraggableSymbol boardSymbol={activeSymbol} isOverlay />
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      </div>

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

      {isSettingsOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 dark:bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('boardSettings')}</h2>
            </div>

            <div className="p-6 space-y-4">
              {saveSuccess && (
                <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-400 px-4 py-3 rounded-lg">
                  {t('settingsSaved')}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('boardName')}
                </label>
                <input
                  type="text"
                  value={boardName}
                  onChange={(e) => setBoardName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  placeholder={t('placeholderName')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('description')}
                </label>
                <textarea
                  value={boardDescription}
                  onChange={(e) => setBoardDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  placeholder={t('optionalDescription')}
                  rows={3}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('category')}
                </label>
                <select
                  value={boardCategory}
                  onChange={(e) => setBoardCategory(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                >
                  <option value="general">{t('categories.general')}</option>
                  <option value="daily">{t('categories.daily')}</option>
                  <option value="social">{t('categories.social')}</option>
                  <option value="education">{t('categories.education')}</option>
                  <option value="medical">{t('categories.medical')}</option>
                  <option value="food">{t('categories.food')}</option>
                </select>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <div className="flex items-center mb-3">
                  <input
                    type="checkbox"
                    id="aiEnabledEdit"
                    checked={aiEnabled}
                    onChange={(e) => setAiEnabled(e.target.checked)}
                    className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                  />
                  <label htmlFor="aiEnabledEdit" className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('enableAI')}
                  </label>
                </div>

                {aiEnabled && (
                  <div className="space-y-4 pl-6">
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t('aiConfigDescription')}
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <label
                        className={`relative block p-3 rounded-lg border transition-colors cursor-pointer ${aiSource === 'primary' ? 'border-indigo-500 ring-2 ring-indigo-200 dark:ring-indigo-400/40' : 'border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-500/60'} ${primaryReady ? '' : 'opacity-60 cursor-not-allowed'}`}
                      >
                        <input
                          type="radio"
                          className="sr-only"
                          checked={aiSource === 'primary'}
                          onChange={() => setAiSource('primary')}
                          disabled={!primaryReady}
                        />
                        <div className="font-semibold text-gray-900 dark:text-gray-100">{t('primaryAI')}</div>
                        <div className="text-sm text-gray-600 dark:text-gray-400 capitalize">
                          {primaryReady ? `${primaryProvider} - ${primaryModel}` : t('notConfigured')}
                        </div>
                      </label>
                      <label
                        className={`relative block p-3 rounded-lg border transition-colors cursor-pointer ${aiSource === 'fallback' ? 'border-indigo-500 ring-2 ring-indigo-200 dark:ring-indigo-400/40' : 'border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-500/60'} ${fallbackReady ? '' : 'opacity-60 cursor-not-allowed'}`}
                      >
                        <input
                          type="radio"
                          className="sr-only"
                          checked={aiSource === 'fallback'}
                          onChange={() => setAiSource('fallback')}
                          disabled={!fallbackReady}
                        />
                        <div className="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                          {t('fallbackAI')}
                          {!fallbackReady && <span className="text-xs text-amber-600">{t('notConfiguredParens')}</span>}
                        </div>
                        <div className="text-sm text-gray-600 dark:text-gray-400 capitalize">
                          {fallbackReady ? `${fallbackProvider} - ${fallbackModel}` : t('setupFallback')}
                        </div>
                      </label>
                    </div>
                    {aiConfigError && (
                      <div className="text-sm text-red-600 dark:text-red-400">{aiConfigError}</div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end space-x-3">
              <button
                onClick={() => setIsSettingsOpen(false)}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                {t('cancel')}
              </button>
              <button
                onClick={handleSaveSettings}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
              >
                {t('saveSettings')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
