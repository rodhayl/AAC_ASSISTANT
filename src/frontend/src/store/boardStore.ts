import { create } from 'zustand';
import type { Board, BoardCreateData, BoardSymbol } from '../types';
import api, { apiOffline, extractError } from '../lib/api';
import i18n from '../i18n/index';
import { useNotificationsStore } from './notificationsStore';

interface BoardState {
  boards: Board[];
  assignedBoards: Board[];
  currentBoard: Board | null;
  // Mutation loading remains separate from read operations so navigation is not blocked by list fetches.
  isLoading: boolean;
  isListLoading: boolean;
  isBoardLoading: boolean;
  error: string | null;
  lastFetchTime: number | null;
  assignedBoardsLastFetchTime: number | null;
  assignedBoardsStudentId?: number;
  isFiltered: boolean;
  
  // Pagination State
  hasMore: boolean;
  page: number;
  
  // Context State for Refresh
  currentUserId?: number;
  currentSearchQuery?: string;
  
  fetchBoards: (userId?: number, name?: string, forceRefresh?: boolean, page?: number) => Promise<void>;
  fetchAssignedBoards: (studentId: number, forceRefresh?: boolean) => Promise<void>;
  fetchBoard: (id: number, forceRefresh?: boolean) => Promise<void>;
  createBoard: (boardData: BoardCreateData, userId: number) => Promise<void>;
  updateBoard: (id: number, boardData: Partial<Board>) => Promise<void>;
  deleteBoard: (id: number, skipRefresh?: boolean) => Promise<void>;
  duplicateBoard: (id: number, userId: number) => Promise<void>;
  addSymbolToBoard: (boardId: number, symbolId: number, position: { x: number, y: number }) => Promise<BoardSymbol>;
  deleteBoardSymbol: (boardId: number, symbolId: number, signal?: AbortSignal) => Promise<void>;
  batchUpdateSymbols: (boardId: number, updates: Array<Record<string, unknown>>) => Promise<void>;
  assignBoardToStudent: (boardId: number, studentId: number, assignedBy?: number) => Promise<void>;
  reset: () => void;
}

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
const PAGE_SIZE = 100;let boardRequestSequence = 0;
let boardsRequestSequence = 0;
let assignedBoardsRequestSequence = 0;
let listRequestCount = 0;
let mutationRequestCount = 0;
let mutationContext = 0;

export const useBoardStore = create<BoardState>((set, get) => {
  const beginMutation = () => {
    const context = mutationContext;
    mutationRequestCount += 1;
    set({ isLoading: true, error: null });
    return context;
  };

  const finishMutation = (context: number, errorMessage?: string) => {
    if (context !== mutationContext) return;
    mutationRequestCount = Math.max(0, mutationRequestCount - 1);
    set(errorMessage
      ? { error: errorMessage, isLoading: mutationRequestCount > 0 }
      : { isLoading: mutationRequestCount > 0 });
  };

  const isCurrentMutation = (context: number) => context === mutationContext;

  /**
   * Reload every page currently held in state, replacing page 1 and appending
   * the rest. Used after a mutation so pagination survives it instead of
   * collapsing to page 1 (D-d).
   */
  const refetchLoadedPages = async (
    userId: number | undefined,
    name: string | undefined,
  ): Promise<void> => {
    const loadedPages = Math.max(get().page, 1);
    for (let page = 1; page <= loadedPages; page += 1) {
      await get().fetchBoards(userId, name, true, page);
    }
  };

  return {
  boards: [],
  assignedBoards: [],
  currentBoard: null,
  isLoading: false,
  error: null,
  lastFetchTime: null,
  assignedBoardsLastFetchTime: null,
  assignedBoardsStudentId: undefined,
  isFiltered: false,
  hasMore: true,
  page: 1,
  currentUserId: undefined,
  currentSearchQuery: '',
  isListLoading: false,
  isBoardLoading: false,

  fetchBoards: async (userId, name, forceRefresh = false, page = 1) => {
    const { lastFetchTime, boards, isFiltered, currentUserId } = get();
    const now = Date.now();
    // Whitespace-only names mean "no filter" (E5 contract): the server
    // treats absent, empty and whitespace-only ``name`` identically — no
    // filter, full list. Omit the param entirely so typing spaces keeps the
    // unfiltered list; the response is identical either way.
    const trimmedName = name?.trim() || undefined;

    // For pagination (page > 1), we append. For page 1, we replace.
    const isPagination = page > 1;

      // Use cache if available and not expired (only if no name filter is applied and current list is not filtered AND we are on page 1)
      if (!forceRefresh && !trimmedName && userId === currentUserId && !isFiltered && !isPagination && lastFetchTime && boards.length > 0 && (now - lastFetchTime) < CACHE_DURATION) {
        return;
      }

      const requestId = ++boardsRequestSequence;
      listRequestCount += 1;
      set({ isListLoading: true, error: null });
      try {
        const params: Record<string, string | number> = {};
        if (userId) params.user_id = userId;
        if (trimmedName) params.name = trimmedName;
        
        // Keep every request on the same fixed page boundary. A refresh must
        // replace page one rather than requesting a larger first page; otherwise
        // a later page request starts at offset 100 and repeatedly re-fetches
        // items already present in state. The requested limit is one row over
        // the boundary so ``hasMore`` is exact instead of inferred from
        // ``length === limit`` (D-d): an exactly-full last page used to keep
        // the "More" control enabled and cost an extra empty fetch.
        const limit = PAGE_SIZE + 1;
        params.skip = (page - 1) * PAGE_SIZE;
        
        params.limit = limit;
        
        const response = await api.get<Board[]>('/boards/', { params });
        const rows = Array.isArray(response.data) ? response.data : [];
        const hasMore = rows.length > PAGE_SIZE;
        // Trim the probe row so page boundaries stay PAGE_SIZE-aligned and no
        // item is ever duplicated between pages.
        const newBoards = hasMore ? rows.slice(0, PAGE_SIZE) : rows;

        if (requestId !== boardsRequestSequence) return;
        // This is the newest list request, so any other in-flight list request
        // is stale and its result will be discarded. Clear the loading flag
        // now: waiting for the stale request to settle would leave the flag
        // stuck when that request finishes last (it is correctly barred from
        // touching the indicator by the requestId check).
        set((state) => {
            const updatedBoards = isPagination ? [...state.boards, ...newBoards] : newBoards;
            
            // Deduplicate by ID just in case
            const uniqueBoards: Board[] = Array.from(
              new Map(updatedBoards.map((b: Board) => [b.id, b])).values()
            );

            return {
              boards: uniqueBoards,
              isListLoading: false,
              isFiltered: !!trimmedName,
              hasMore,
              page,
              lastFetchTime: !trimmedName && page === 1 ? now : state.lastFetchTime,
              currentUserId: userId,
              currentSearchQuery: trimmedName
            };
        });
      } catch (error: unknown) {
        if (requestId === boardsRequestSequence) {
          set({
            error: extractError(error, 'Failed to fetch boards'),
            isListLoading: false,
          });
        }
      } finally {
        listRequestCount = Math.max(0, listRequestCount - 1);
        // Safety net: a request from a previous auth context must not clear a
        // newer request's indicator, so only the newest request may reset it.
        if (requestId === boardsRequestSequence && listRequestCount === 0) {
          set({ isListLoading: false });
        }
      }

  },

  fetchBoard: async (id, forceRefresh = false) => {
    const { currentBoard } = get();
    
    // Use cached board if it's the same one
    if (!forceRefresh && currentBoard && currentBoard.id === id) {
      return;
    }

    const requestId = ++boardRequestSequence;
    set({
      isBoardLoading: true,
      error: null,
      currentBoard: currentBoard?.id === id ? currentBoard : null,
    });
    try {
      const response = await api.get(`/boards/${id}`);
      if (requestId !== boardRequestSequence) return;
      set({
        currentBoard: response.data,
        isBoardLoading: false,
      });
    } catch (error: unknown) {
      if (requestId === boardRequestSequence) {
        set({ error: extractError(error, i18n.t('boards:boardLoadFailed')), isBoardLoading: false });
      }
    }
  },

  createBoard: async (boardData: BoardCreateData, userId) => {
    const context = beginMutation();
    try {
      await api.post('/boards/', boardData, {
        params: { user_id: userId } // In real app, userId comes from token
      });
      if (!isCurrentMutation(context)) return;
      const { currentUserId, currentSearchQuery } = get();
      // Reload every loaded page (not just page 1) so creating a board does
      // not collapse a paginated list the user is browsing (D-d).
      await refetchLoadedPages(currentUserId, currentSearchQuery);
      finishMutation(context);
    } catch (error: unknown) {
      finishMutation(context, extractError(error, 'Failed to create board'));
      throw error;
    }
  },

  updateBoard: async (id, boardData) => {
    const context = beginMutation();
    try {
      const response = await api.put(`/boards/${id}`, boardData);
      if (!isCurrentMutation(context)) return;
      set((state) => ({
        boards: state.boards.map(b => b.id === id ? response.data : b),
        currentBoard: state.currentBoard?.id === id ? response.data : state.currentBoard,
      }));
      finishMutation(context);
    } catch (error: unknown) {
      finishMutation(context, extractError(error, 'Failed to update board'));
      throw error;
    }
  },

  deleteBoard: async (id, skipRefresh = false) => {
    const context = beginMutation();
    try {
      await api.delete(`/boards/${id}`);
      if (!isCurrentMutation(context)) return;
      
      if (skipRefresh) {
        set((state) => ({
          boards: state.boards.filter(b => b.id !== id),
          currentBoard: state.currentBoard?.id === id ? null : state.currentBoard,
        }));
        finishMutation(context);
      } else {
        const { currentUserId, currentSearchQuery } = get();
        // Reload every page currently in state. Refreshing only page 1 dropped
        // pages 2+ that the user had already loaded (D-d); deleting an item
        // must not collapse their list back to the first page.
        await refetchLoadedPages(currentUserId, currentSearchQuery);
        if (!isCurrentMutation(context)) return;
        finishMutation(context);
      }
    } catch (error: unknown) {
      finishMutation(context, extractError(error, 'Failed to delete board'));
      throw error;
    }
  },

  duplicateBoard: async (id, userId) => {
    const context = beginMutation();
    // The new board's id once it exists, so a mid-copy failure or a stale
    // mutation (token/logout/board switch) can remove the half-duplicated
    // board instead of leaving it for manual deletion (H57 + B4).
    let newBoardId: number | null = null;
    // Best-effort removal of a partial copy. Cancellation must not surface as
    // an error (the newer mutation owns the UI state), so cleanup failures are
    // only logged.
    const discardPartialCopy = async () => {
      if (newBoardId === null) return;
      try {
        await api.delete(`/boards/${newBoardId}`);
      } catch (cleanupError) {
        console.error('Failed to clean up a partially duplicated board', cleanupError);
      }
    };
    try {
      if (apiOffline.isOffline()) {
        throw new Error(
          i18n.t('boards:offlineDuplicateUnsupported'),
        );
      }
      const base: Board = (await api.get(`/boards/${id}`)).data;
      if (!isCurrentMutation(context)) return;
      // Preserve grid, locale and the language-learning flag so a duplicate is
      // a faithful copy. AI content generation is intentionally NOT triggered
      // on duplicate: the board is created with AI disabled, its symbols are
      // copied manually, and AI settings are restored via the update endpoint.
      const createRes = await api.post('/boards/', {
        name: `${base.name}${i18n.t('boards:copySuffix')}`,
        description: base.description,
        category: base.category,
        is_public: base.is_public,
        is_template: base.is_template,
        grid_rows: base.grid_rows ?? 4,
        grid_cols: base.grid_cols ?? 5,
        locale: base.locale ?? 'en',
        is_language_learning: base.is_language_learning ?? false,
        ai_enabled: false
      }, { params: { user_id: userId } });
      // Capture the id before any stale check: the board exists server-side
      // the moment the POST resolves, so every later exit must be able to
      // remove it (B4).
      newBoardId = createRes.data.id;
      const newBoard = createRes.data;
      if (!isCurrentMutation(context)) {
        await discardPartialCopy();
        return;
      }
      // A copied symbol keeps its folder link only when the new owner can
      // actually view the target board. Resolving every link before the first
      // symbol POST prevents a mid-way 403 from orphaning a partial copy, and
      // avoids copying broken links (private boards of the original owner,
      // boards deleted since the source board was built).
      const effectiveLinkedIds = new Map<number, number | null>();
      for (const s of base.symbols || []) {
        if (!isCurrentMutation(context)) {
          await discardPartialCopy();
          return;
        }
        if (s.linked_board_id == null) {
          effectiveLinkedIds.set(s.id, null);
          continue;
        }
        try {
          await api.get(`/boards/${s.linked_board_id}`, {
            params: { skip_translation: true },
          });
          if (!isCurrentMutation(context)) {
            await discardPartialCopy();
            return;
          }
          effectiveLinkedIds.set(s.id, s.linked_board_id);
        } catch {
          if (!isCurrentMutation(context)) {
            await discardPartialCopy();
            return;
          }
          effectiveLinkedIds.set(s.id, null);
        }
      }
      for (const s of base.symbols || []) {
        if (!isCurrentMutation(context)) {
          await discardPartialCopy();
          return;
        }
        await api.post(`/boards/${newBoard.id}/symbols`, {
          symbol_id: s.symbol?.id ?? s.symbol_id,
          position_x: s.position_x,
          position_y: s.position_y,
          size: s.size,
          is_visible: s.is_visible,
          custom_text: s.custom_text,
          color: s.color ?? null,
          linked_board_id: effectiveLinkedIds.get(s.id) ?? null
        });
      }
      // Only restore AI settings the source board can actually supply: the API
      // rejects `ai_enabled` without a provider and model, and seeded/template
      // boards legitimately have AI enabled with no provider configured. A
      // missing setting must not fail the whole copy (the duplicate keeps AI
      // off, everything else is preserved).
      if (base.ai_enabled && base.ai_provider && base.ai_model) {
        if (!isCurrentMutation(context)) {
          await discardPartialCopy();
          return;
        }
        await api.put(`/boards/${newBoard.id}`, {
          ai_enabled: true,
          ai_provider: base.ai_provider,
          ai_model: base.ai_model
        });
      }
      if (!isCurrentMutation(context)) {
        await discardPartialCopy();
        return;
      }
      await refetchLoadedPages(userId, get().currentSearchQuery);
      if (!isCurrentMutation(context)) {
        await discardPartialCopy();
        return;
      }
      finishMutation(context);
    } catch (e: unknown) {
      await discardPartialCopy();
      finishMutation(context, extractError(e, 'Failed to duplicate board'));
      throw e;
    }
  },

  fetchAssignedBoards: async (studentId, forceRefresh = false) => {
    const { assignedBoardsLastFetchTime, assignedBoards, assignedBoardsStudentId } = get();
    const now = Date.now();
    if (
      !forceRefresh &&
      assignedBoardsLastFetchTime &&
      assignedBoardsStudentId === studentId &&
      assignedBoards.length > 0 &&
      now - assignedBoardsLastFetchTime < CACHE_DURATION
    ) {
      return;
    }
    const requestId = ++assignedBoardsRequestSequence;
    listRequestCount += 1;
    set({ isListLoading: true, error: null });
    try {
      const response = await api.get('/boards/assigned', { params: { student_id: studentId } });
      if (requestId === assignedBoardsRequestSequence) {
        // Newest request wins; stale in-flight ones are ignored, so clear the
        // loading flag instead of counting them (see fetchBoards).
        set({
          assignedBoards: response.data,
          isListLoading: false,
          assignedBoardsLastFetchTime: now,
          assignedBoardsStudentId: studentId,
        });
      }
    } catch (error: unknown) {
      if (requestId === assignedBoardsRequestSequence) {
        set({
          error: extractError(error, 'Failed to fetch assigned boards'),
          isListLoading: false,
        });
      }
    } finally {
      listRequestCount = Math.max(0, listRequestCount - 1);
      // A request from a previous auth context may finish after a new request
      // starts. It must not clear the new user's loading indicator.
      if (requestId === assignedBoardsRequestSequence && listRequestCount === 0) {
        set({ isListLoading: false });
      }
    }

  },

  addSymbolToBoard: async (boardId, symbolId, position) => {
    const context = beginMutation();
    try {
      const response = await api.post(`/boards/${boardId}/symbols`, {
        symbol_id: symbolId,
        position_x: position.x,
        position_y: position.y,
        size: 1,
        is_visible: true
      });
      if (!isCurrentMutation(context)) return response.data;
      
      // Update current board if it's the one being modified
      const currentBoard = get().currentBoard;
      if (currentBoard && currentBoard.id === boardId) {
        set({
          currentBoard: {
            ...currentBoard,
            symbols: [...currentBoard.symbols, response.data]
          }
        });
      }
      finishMutation(context);
      return response.data;
    } catch (error: unknown) {
      finishMutation(context, extractError(error, 'Failed to add symbol'));
      throw error;
    }
  },

  deleteBoardSymbol: async (boardId, symbolId, signal) => {
    const context = beginMutation();
    try {
      await api.delete(`/boards/${boardId}/symbols/${symbolId}`, { signal });
      if (!isCurrentMutation(context)) return;
      
      // Update current board symbols
      const currentBoard = get().currentBoard;
      if (currentBoard && currentBoard.id === boardId) {
        set({
          currentBoard: {
            ...currentBoard,
            symbols: currentBoard.symbols.filter(s => s.id !== symbolId)
          }
        });
      }
      finishMutation(context);
    } catch (error: unknown) {
      finishMutation(context, extractError(error, 'Failed to delete symbol'));
      throw error;
    }
  },

  batchUpdateSymbols: async (boardId, updates) => {
    const context = beginMutation();
    try {
      await api.put(`/boards/${boardId}/symbols/batch`, updates);
      if (!isCurrentMutation(context)) return;
      
      // Refresh the board to get updated symbols
      await get().fetchBoard(boardId, true);
      if (!isCurrentMutation(context)) return;
      finishMutation(context);
    } catch (error: unknown) {
      finishMutation(context, extractError(error, 'Failed to batch update symbols'));
      throw error;
    }
  },

  reset: () => {
    boardRequestSequence += 1;
    boardsRequestSequence += 1;
    assignedBoardsRequestSequence += 1;
    mutationContext += 1;
    mutationRequestCount = 0;
    set({
      boards: [],
      assignedBoards: [],
      currentBoard: null,
      isLoading: false,
      isListLoading: false,
      isBoardLoading: false,
      error: null,
      lastFetchTime: null,
      assignedBoardsLastFetchTime: null,
      assignedBoardsStudentId: undefined,
      isFiltered: false,
      hasMore: true,
      page: 1,
      currentUserId: undefined,
      currentSearchQuery: '',
    });
  },

  assignBoardToStudent: async (boardId, studentId, assignedBy) => {
    const context = beginMutation();
    try {
      await api.post(`/boards/${boardId}/assign`, {
        student_id: studentId,
        assigned_by: assignedBy
      });
      if (!isCurrentMutation(context)) return;
      set((state) => ({
        assignedBoardsLastFetchTime:
          state.assignedBoardsStudentId === studentId ? null : state.assignedBoardsLastFetchTime,
      }));
      useNotificationsStore.getState().add({
        title: i18n.t('boards:boardAssigned'),
        message: i18n.t('boards:boardAssignedTo', { boardId, studentId }),
      })
      finishMutation(context);
    } catch (e: unknown) {
      finishMutation(context, extractError(e, 'Failed to assign board'));
      throw e;
    }
  }
  };
});

if (typeof window !== 'undefined') {
  const resetForAuthContextChange = () => {
    useBoardStore.getState().reset();
  };
  window.addEventListener('aac:auth-logout', resetForAuthContextChange);
  window.addEventListener('aac:auth-context-changed', resetForAuthContextChange);
}
