import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Board, BoardSymbol } from '../types';
import type { AISuggestion } from '../components/board/AISuggestionPanel';
import type { BoardPosition } from './useBoardCollab';
import { extractError } from '../lib/api';

interface UseBoardAISuggestionsOptions {
  currentBoard: Board | null;
  localSymbols: BoardSymbol[];
  resolvedProvider?: string;
  resolvedModel?: string;
  fetchBoard: (id: number, forceRefresh?: boolean) => Promise<void>;
  deleteBoardSymbol: (boardId: number, symbolId: number) => Promise<void>;
  setHasChanges: (hasChanges: boolean) => void;
}

export function useBoardAISuggestions({
  currentBoard,
  localSymbols,
  resolvedProvider,
  resolvedModel,
  fetchBoard,
  deleteBoardSymbol,
  setHasChanges,
}: UseBoardAISuggestionsOptions) {
  const { t } = useTranslation('boards');
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [applyId, setApplyId] = useState<string | null>(null);
  const [refinePrompt, setRefinePrompt] = useState('');
  const [applyAllLoading, setApplyAllLoading] = useState(false);

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
      const body: Record<string, unknown> = {};
      if (options?.refinePrompt) body.refine_prompt = options.refinePrompt;
      if (options?.regenerate) body.regenerate = true;
      const response = await api.post(`/boards/${currentBoard.id}/ai/suggestions`, body);
      const items: AISuggestion[] = response.data.items || [];
      setAiSuggestions(items);
      if (!items.length) setAiError(t('noSuggestions'));
    } catch (error: unknown) {
      setAiError(extractError(error, t('failedToLoadSuggestions')));
      setAiSuggestions([]);
    } finally {
      setAiLoading(false);
    }
  }, [currentBoard, resolvedModel, resolvedProvider, t]);

  const handleRefine = useCallback(() => {
    const prompt = refinePrompt.trim();
    if (!prompt) {
      setAiError(t('refinePromptRequired'));
      return;
    }
    void loadAISuggestions({ refinePrompt: prompt, regenerate: false });
  }, [loadAISuggestions, refinePrompt, t]);

  const handleRegenerate = useCallback(() => {
    const prompt = refinePrompt.trim();
    void loadAISuggestions({ refinePrompt: prompt || undefined, regenerate: true });
  }, [loadAISuggestions, refinePrompt]);

  const applySuggestion = useCallback(async (item: AISuggestion, position?: BoardPosition) => {
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
        const existing = currentBoard.symbols?.find(
          (symbol) => symbol.position_x === position.x && symbol.position_y === position.y,
        );
        if (existing) await deleteBoardSymbol(currentBoard.id, existing.id);
      }
      await api.post(`/boards/${currentBoard.id}/ai/suggestions/apply`, {
        item,
        position_x: position?.x,
        position_y: position?.y,
      });
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
    } catch (error: unknown) {
      setAiError(extractError(error, t('failedToAddSuggestion')));
    } finally {
      setApplyId(null);
    }
  }, [currentBoard, deleteBoardSymbol, fetchBoard, localSymbols, setHasChanges, t]);

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
        } catch (error: unknown) {
          failures.push(`${item.label}: ${extractError(error, 'unknown error')}`);
        }
      }
      await fetchBoard(currentBoard.id, true);
      setHasChanges(true);
    } catch (error: unknown) {
      setAiError(extractError(error, t('failedToAddAll')));
    } finally {
      if (failures.length) {
        setAiError(t('addSuggestionResult', {
          success: successCount,
          total: aiSuggestions.length,
          failures: failures.join('; '),
        }));
      }
      setApplyAllLoading(false);
    }
  }, [aiSuggestions, currentBoard, fetchBoard, localSymbols, setHasChanges, t]);

  return {
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
  };
}
