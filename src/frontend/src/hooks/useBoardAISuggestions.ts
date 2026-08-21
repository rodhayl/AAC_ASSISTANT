import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getBoardCapacity } from '../lib/boardGrid';
import { extractError } from '../lib/api';
import type { Board, BoardSymbol } from '../types';
import type { AISuggestion } from '../components/board/AISuggestionPanel';
import type { BoardPosition } from './useBoardCollab';

interface UseBoardAISuggestionsOptions {
  currentBoard: Board | null;
  localSymbols: BoardSymbol[];
  resolvedProvider?: string;
  resolvedModel?: string;
  fetchBoard: (id: number, forceRefresh?: boolean) => Promise<void>;
  setHasChanges: (hasChanges: boolean) => void;
}

export function useBoardAISuggestions({
  currentBoard,
  localSymbols,
  resolvedProvider,
  resolvedModel,
  fetchBoard,
  setHasChanges,
}: UseBoardAISuggestionsOptions) {
  const { t } = useTranslation('boards');
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [applyId, setApplyId] = useState<string | null>(null);
  const [refinePrompt, setRefinePrompt] = useState('');
  const [applyAllLoading, setApplyAllLoading] = useState(false);
  const suggestionGeneration = useRef(0);
  const suggestionController = useRef<AbortController | null>(null);
  const applyController = useRef<AbortController | null>(null);
  const cancelActiveApply = useCallback(() => {
    applyController.current?.abort();
    applyController.current = null;
    setApplyId(null);
    setApplyAllLoading(false);
  }, []);

  useEffect(() => {
    suggestionGeneration.current += 1;
    suggestionController.current?.abort();
    suggestionController.current = null;
    cancelActiveApply();
    setAiSuggestions([]);
    setAiError(null);
    setAiLoading(false);
    setApplyId(null);
    setApplyAllLoading(false);

    return () => {
      suggestionGeneration.current += 1;
      suggestionController.current?.abort();
      suggestionController.current = null;
      cancelActiveApply();
    };
  }, [cancelActiveApply, currentBoard?.id, currentBoard?.ai_enabled, resolvedProvider, resolvedModel]);

  const loadAISuggestions = useCallback(async (options?: { refinePrompt?: string; regenerate?: boolean }) => {
    if (!currentBoard?.ai_enabled) return;
    if (!resolvedProvider || !resolvedModel) {
      setAiError(t('aiSettingsMissing'));
      return;
    }

    const generation = ++suggestionGeneration.current;
    suggestionController.current?.abort();
    cancelActiveApply();
    const controller = new AbortController();
    suggestionController.current = controller;
    setAiLoading(true);
    setAiError(null);
    try {
      const api = (await import('../lib/api')).default;
      const body: Record<string, unknown> = {};
      if (options?.refinePrompt) body.refine_prompt = options.refinePrompt;
      if (options?.regenerate) body.regenerate = true;
      const response = await api.post(`/boards/${currentBoard.id}/ai/suggestions`, body, {
        signal: controller.signal,
      });
      if (generation !== suggestionGeneration.current) return;
      const items: AISuggestion[] = response.data.items || [];
      setAiSuggestions(items);
      if (!items.length) setAiError(t('noSuggestions'));
    } catch (error: unknown) {
      if (generation !== suggestionGeneration.current || controller.signal.aborted) return;
      setAiError(extractError(error, t('failedToLoadSuggestions')));
      setAiSuggestions([]);
    } finally {
      if (generation === suggestionGeneration.current) {
        setAiLoading(false);
        if (suggestionController.current === controller) suggestionController.current = null;
      }
    }
  }, [cancelActiveApply, currentBoard, resolvedModel, resolvedProvider, t]);

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
    const capacity = getBoardCapacity(currentBoard);
    const filled = Math.max(localSymbols.length, currentBoard.symbols?.length ?? 0);
    if (!position && filled >= capacity) {
      setAiError(t('boardFull'));
      return;
    }
    const boardId = currentBoard.id;
    const generation = suggestionGeneration.current;
    cancelActiveApply();
    const controller = new AbortController();
    applyController.current = controller;
    const isCurrentApply = () =>
      generation === suggestionGeneration.current &&
      applyController.current === controller &&
      !controller.signal.aborted;
    setApplyId(item.label);
    try {
      const api = (await import('../lib/api')).default;
      if (!isCurrentApply()) return;
      // The backend replaces the occupying placement atomically when an
      // explicit position is given, so no delete-first round trip is needed
      // here — that two-step approach could lose the existing symbol if the
      // apply request failed in between.
      await api.post(`/boards/${boardId}/ai/suggestions/apply`, {
        item,
        position_x: position?.x,
        position_y: position?.y,
      }, {
        signal: controller.signal,
      });
      if (!isCurrentApply()) return;
      await fetchBoard(boardId, true);
      if (isCurrentApply()) setHasChanges(true);
    } catch (error: unknown) {
      if (isCurrentApply()) {
        setAiError(extractError(error, t('failedToAddSuggestion')));
      }
    } finally {
      if (isCurrentApply()) {
        applyController.current = null;
        setApplyId(null);
      }
    }
  }, [cancelActiveApply, currentBoard, fetchBoard, localSymbols, setHasChanges, t]);

  const applyAllSuggestions = useCallback(async () => {
    if (!currentBoard || !aiSuggestions.length) return;
    const capacity = getBoardCapacity(currentBoard);
    const filled = Math.max(localSymbols.length, currentBoard.symbols?.length ?? 0);
    const remaining = capacity - filled;
    if (remaining <= 0) {
      setAiError(t('boardFull'));
      return;
    }
    const boardId = currentBoard.id;
    const generation = suggestionGeneration.current;
    cancelActiveApply();
    const controller = new AbortController();
    applyController.current = controller;
    const isCurrentApply = () =>
      generation === suggestionGeneration.current &&
      applyController.current === controller &&
      !controller.signal.aborted;
    setApplyAllLoading(true);
    setAiError(null);
    let successCount = 0;
    const failures: string[] = [];
    try {
      const api = (await import('../lib/api')).default;
      for (const item of aiSuggestions) {
        if (!isCurrentApply()) return;
        if (successCount >= remaining) {
          failures.push(t('boardFullSkipped'));
          break;
        }
        try {
          await api.post(`/boards/${boardId}/ai/suggestions/apply`, { item }, {
            signal: controller.signal,
          });
          if (!isCurrentApply()) return;
          successCount += 1;
        } catch (error: unknown) {
          if (!isCurrentApply()) return;
          failures.push(`${item.label}: ${extractError(error, t('unknownError', 'Unknown error'))}`);
        }
      }
      if (!isCurrentApply()) return;
      await fetchBoard(boardId, true);
      if (isCurrentApply()) setHasChanges(true);
    } catch (error: unknown) {
      if (isCurrentApply()) {
        setAiError(extractError(error, t('failedToAddAll')));
      }
    } finally {
      if (isCurrentApply()) {
        applyController.current = null;
        if (failures.length) {
          setAiError(t('addSuggestionResult', {
            success: successCount,
            total: aiSuggestions.length,
            failures: failures.join('; '),
          }));
        }
        setApplyAllLoading(false);
      }
    }
  }, [aiSuggestions, cancelActiveApply, currentBoard, fetchBoard, localSymbols, setHasChanges, t]);

  return {
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
  };
}
