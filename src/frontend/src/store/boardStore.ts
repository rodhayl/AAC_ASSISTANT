import { create } from 'zustand';
import type { Board, BoardSymbol } from '../types';
import api, { apiOffline, extractError } from '../lib/api';
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createBoard: (boardData: any, userId: number) => Promise<void>;
  updateBoard: (id: number, boardData: Partial<Board>) => Promise<void>;
  deleteBoard: (id: number, skipRefresh?: boolean) => Promise<void>;
  duplicateBoard: (id: number, userId: number) => Promise<void>;
  addSymbolToBoard: (boardId: number, symbolId: number, position: { x: number, y: number }) => Promise<BoardSymbol>;
  deleteBoardSymbol: (boardId: number, symbolId: number, signal?: AbortSignal) => Promise<void>;
  batchUpdateSymbols: (boardId: number, updates: Array<Record<string, unknown>>) => Promise<void>;
  assignBoardToStudent: (boardId: number, studentId: number, assignedBy?: number) => Promise<void>;
}

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
const PAGE_SIZE = 100;

let boardRequestSequence = 0;
let boardsRequestSequence = 0;
let assignedBoardsRequestSequence = 0;
let listRequestCount = 0;
let mutationRequestCount = 0;

export const useBoardStore = create<BoardState>((set, get) => {
  const beginMutation = () => {
    mutationRequestCount += 1;
    set({ isLoading: true, error: null });
  };

  const finishMutation = (errorMessage?: string) => {
    mutationRequestCount = Math.max(0, mutationRequestCount - 1);
    set(errorMessage
      ? { error: errorMessage, isLoading: mutationRequestCount > 0 }
      : { isLoading: mutationRequestCount > 0 });
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
    
    // For pagination (page > 1), we append. For page 1, we replace.
    const isPagination = page > 1;

      // Use cache if available and not expired (only if no name filter is applied and current list is not filtered AND we are on page 1)
      if (!forceRefresh && !name && userId === currentUserId && !isFiltered && !isPagination && lastFetchTime && boards.length > 0 && (now - lastFetchTime) < CACHE_DURATION) {
        return;
      }

      const requestId = ++boardsRequestSequence;
      listRequestCount += 1;
      set({ isListLoading: true, error: null });
      try {
        const params: Record<string, string | number> = {};
        if (userId) params.user_id = userId;
        if (name) params.name = name;
        
        let limit = PAGE_SIZE;
        if (forceRefresh && page === 1 && boards.length > PAGE_SIZE) {
            // If we have more than one page loaded, try to fetch enough to cover what we have
            // Round up to nearest PAGE_SIZE
            limit = Math.ceil(boards.length / PAGE_SIZE) * PAGE_SIZE;
        }

        params.skip = (page - 1) * limit;

        if (page > 1) {
            params.skip = (page - 1) * PAGE_SIZE;
            limit = PAGE_SIZE; // Enforce standard page size for subsequent pages
        }
        
        params.limit = limit;
        
        const response = await api.get<Board[]>('/boards/', { params });
        const newBoards = response.data;
        
        const hasMore = newBoards.length === limit;

        if (requestId !== boardsRequestSequence) return;
        set((state) => {
            const updatedBoards = isPagination ? [...state.boards, ...newBoards] : newBoards;
            
            // Deduplicate by ID just in case
            const uniqueBoards: Board[] = Array.from(
              new Map(updatedBoards.map((b: Board) => [b.id, b])).values()
            );

            return {
              boards: uniqueBoards,
              isListLoading: listRequestCount > 1,
              isFiltered: !!name,
              hasMore,
              page,
              lastFetchTime: !name && page === 1 ? now : state.lastFetchTime,
              currentUserId: userId,
              currentSearchQuery: name
            };
        });
      } catch (error: unknown) {
      if (requestId === boardsRequestSequence) {
        set({ error: extractError(error, 'Failed to fetch boards'), isListLoading: listRequestCount > 1 });
      }
    } finally {
      listRequestCount = Math.max(0, listRequestCount - 1);
      if (listRequestCount === 0) set({ isListLoading: false });
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
      console.error('Fetch board error:', error);
      if (requestId === boardRequestSequence) {
        set({ error: extractError(error, 'Failed to fetch board'), isBoardLoading: false });
      }
    }
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createBoard: async (boardData: any, userId) => {
    beginMutation();
    try {
      await api.post('/boards/', boardData, {
        params: { user_id: userId } // In real app, userId comes from token
      });
      const { currentUserId, currentSearchQuery } = get();
      await get().fetchBoards(currentUserId, currentSearchQuery, true, 1);
      finishMutation();
    } catch (error: unknown) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (typeof error === 'object' && error && (error as any).message === 'offline') {
        // Offline handling logic if needed
      }
      finishMutation(extractError(error, 'Failed to create board'));
      throw error;
    }
  },

  updateBoard: async (id, boardData) => {
    beginMutation();
    try {
      const response = await api.put(`/boards/${id}`, boardData);
      set((state) => ({
        boards: state.boards.map(b => b.id === id ? response.data : b),
        currentBoard: state.currentBoard?.id === id ? response.data : state.currentBoard,
      }));
      finishMutation();
    } catch (error: unknown) {
      finishMutation(extractError(error, 'Failed to update board'));
      throw error;
    }
  },

  deleteBoard: async (id, skipRefresh = false) => {
    beginMutation();
    try {
      await api.delete(`/boards/${id}`);
      
      if (skipRefresh) {
        set((state) => ({
          boards: state.boards.filter(b => b.id !== id),
          currentBoard: state.currentBoard?.id === id ? null : state.currentBoard,
        }));
        finishMutation();
      } else {
        const { currentUserId, currentSearchQuery } = get();
        // Always refresh page 1 to handle pagination gaps correctly
        await get().fetchBoards(currentUserId, currentSearchQuery, true, 1);
        finishMutation();
      }
    } catch (error: unknown) {
      finishMutation(extractError(error, 'Failed to delete board'));
      throw error;
    }
  },

  duplicateBoard: async (id, userId) => {
    beginMutation();
    try {
      const offline = apiOffline.isOffline()
      let base: Board
      if (offline) {
        const found = get().boards.find(b => b.id === id) || get().currentBoard
        if (!found || found.id !== id) throw new Error('Source board unavailable offline')
        base = found
      } else {
        base = (await api.get(`/boards/${id}`)).data
      }
      const createRes = await api.post('/boards/', {
        name: `${base.name} (Copy)`,
        description: base.description,
        category: base.category,
        is_public: base.is_public,
        is_template: base.is_template
      }, { params: { user_id: userId } });
      const newBoard = createRes.data;
      for (const s of base.symbols || []) {
        await api.post(`/boards/${newBoard.id}/symbols`, {
          symbol_id: s.symbol?.id ?? s.symbol_id,
          position_x: s.position_x,
          position_y: s.position_y,
          size: s.size,
          is_visible: s.is_visible,
          custom_text: s.custom_text
        });
      }
      await get().fetchBoards(userId, get().currentSearchQuery, true, 1);
      finishMutation();
    } catch (e: unknown) {
      finishMutation(extractError(e, 'Failed to duplicate board'));
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
        set({
          assignedBoards: response.data,
          isListLoading: listRequestCount > 1,
          assignedBoardsLastFetchTime: now,
          assignedBoardsStudentId: studentId,
        });
      }
    } catch (error: unknown) {
      if (requestId === assignedBoardsRequestSequence) {
        set({ error: extractError(error, 'Failed to fetch assigned boards'), isListLoading: listRequestCount > 1 });
      }
    } finally {
      listRequestCount = Math.max(0, listRequestCount - 1);
      if (listRequestCount === 0) set({ isListLoading: false });
    }
  },

  addSymbolToBoard: async (boardId, symbolId, position) => {
    beginMutation();
    try {
      const response = await api.post(`/boards/${boardId}/symbols`, {
        symbol_id: symbolId,
        position_x: position.x,
        position_y: position.y,
        size: 1,
        is_visible: true
      });
      
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
      finishMutation();
      return response.data;
    } catch (error: unknown) {
      finishMutation(extractError(error, 'Failed to add symbol'));
      throw error;
    }
  },

  deleteBoardSymbol: async (boardId, symbolId, signal) => {
    beginMutation();
    try {
      await api.delete(`/boards/${boardId}/symbols/${symbolId}`, { signal });
      
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
      finishMutation();
    } catch (error: unknown) {
      finishMutation(extractError(error, 'Failed to delete symbol'));
      throw error;
    }
  },

  batchUpdateSymbols: async (boardId, updates) => {
    beginMutation();
    try {
      await api.put(`/boards/${boardId}/symbols/batch`, updates);
      
      // Refresh the board to get updated symbols
      await get().fetchBoard(boardId, true);
      finishMutation();
    } catch (error: unknown) {
      finishMutation(extractError(error, 'Failed to batch update symbols'));
      throw error;
    }
  },

  assignBoardToStudent: async (boardId, studentId, assignedBy) => {
    beginMutation();
    try {
      await api.post(`/boards/${boardId}/assign`, {
        student_id: studentId,
        assigned_by: assignedBy
      });
      set((state) => ({
        assignedBoardsLastFetchTime:
          state.assignedBoardsStudentId === studentId ? null : state.assignedBoardsLastFetchTime,
      }));
      try {
        useNotificationsStore.getState().add({ title: 'Board assigned', message: `Board ${boardId} assigned to student ${studentId}` })
      } catch { /* notification optional */ }
      finishMutation();
    } catch (e: unknown) {
      finishMutation(extractError(e, 'Failed to assign board'));
      throw e;
    }
  }
  };
});
