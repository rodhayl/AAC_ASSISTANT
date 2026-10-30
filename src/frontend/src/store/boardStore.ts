import { create } from 'zustand';
import type { Board, BoardSymbol } from '../types';
import api, { apiOffline } from '../lib/api';
import { useNotificationsStore } from './notificationsStore';

interface BoardState {
  boards: Board[];
  assignedBoards: Board[];
  currentBoard: Board | null;
  isLoading: boolean;
  error: string | null;
  lastFetchTime: number | null;
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
  updateBoardSymbol: (boardId: number, symbolId: number, updates: Record<string, unknown>) => Promise<void>;
  deleteBoardSymbol: (boardId: number, symbolId: number) => Promise<void>;
  batchUpdateSymbols: (boardId: number, updates: Array<Record<string, unknown>>) => Promise<void>;
  assignBoardToStudent: (boardId: number, studentId: number, assignedBy?: number) => Promise<void>;
  unassignBoardFromStudent: (boardId: number, studentId: number) => Promise<void>;
}

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
const PAGE_SIZE = 100;

function extractError(error: unknown, fallback: string): string {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const r = error as { response?: { data?: { detail?: any } } };
  const d = r.response?.data?.detail;
  if (Array.isArray(d)) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return d.map((e: any) => e.msg).join(', ');
  }
  if (typeof d === 'string') return d;
  if (d) return JSON.stringify(d);
  return fallback;
}

export const useBoardStore = create<BoardState>((set, get) => ({
  boards: [],
  assignedBoards: [],
  currentBoard: null,
  isLoading: false,
  error: null,
  lastFetchTime: null,
  isFiltered: false,
  hasMore: true,
  page: 1,
  currentUserId: undefined,
  currentSearchQuery: '',

  fetchBoards: async (userId, name, forceRefresh = false, page = 1) => {
    const { lastFetchTime, boards, isFiltered } = get();
    const now = Date.now();
    
    // Reset state if name filter changes or explicit page 1 fetch
    // const isNewSearch = name !== get().currentSearchQuery; // Unused
    
    // For pagination (page > 1), we append. For page 1, we replace.
    const isPagination = page > 1;

      // Use cache if available and not expired (only if no name filter is applied and current list is not filtered AND we are on page 1)
      if (!forceRefresh && !name && !userId && !isFiltered && !isPagination && lastFetchTime && boards.length > 0 && (now - lastFetchTime) < CACHE_DURATION) {
        return;
      }

      set({ isLoading: true, error: null });
      try {
        const params: Record<string, string | number> = {};
        if (userId) params.user_id = userId;
        if (name) params.name = name;
        
        // If force refresh and page=1, we might want to fetch more if the user already has more loaded
        // BUT simplicity first: if force refresh, we reset to page 1.
        // The issue is that the user perceives "disappearing" boards.
        // If we want to keep the current number of items, we would need to fetch limit = current items count (rounded up to page size)
        
        let limit = PAGE_SIZE;
        if (forceRefresh && page === 1 && boards.length > PAGE_SIZE) {
            // If we have more than one page loaded, try to fetch enough to cover what we have
            // Round up to nearest PAGE_SIZE
            limit = Math.ceil(boards.length / PAGE_SIZE) * PAGE_SIZE;
        }

        params.skip = (page - 1) * limit; // This might be weird if page > 1 and we changed limit. 
        // Actually, if page > 1, we shouldn't change limit because pagination logic expects PAGE_SIZE chunks.
        // So ONLY change limit if page === 1.
        
        if (page > 1) {
            params.skip = (page - 1) * PAGE_SIZE;
            limit = PAGE_SIZE; // Enforce standard page size for subsequent pages
        }
        
        params.limit = limit;
        
        const response = await api.get<Board[]>('/boards/', { params });
        const newBoards = response.data;
        
        // Calculate if there are more
        // If we fetched a large batch, hasMore logic needs to check if we got full batch
        const hasMore = newBoards.length === limit;

        set((state) => {
            const updatedBoards = isPagination ? [...state.boards, ...newBoards] : newBoards;
            
            // Deduplicate by ID just in case
            const uniqueBoards: Board[] = Array.from(
              new Map(updatedBoards.map((b: Board) => [b.id, b])).values()
            );

            return {
              boards: uniqueBoards,
              isLoading: false,
              isFiltered: !!name,
              hasMore,
              page: page, // We stay on page 1 if we refreshed page 1
              lastFetchTime: !name && page === 1 ? now : state.lastFetchTime,
              currentUserId: userId,
              currentSearchQuery: name
            };
        });
      } catch (error: unknown) {
      set({ error: extractError(error, 'Failed to fetch boards'), isLoading: false });
    }
  },

  fetchBoard: async (id, forceRefresh = false) => {
    const { currentBoard } = get();
    
    // Use cached board if it's the same one
    if (!forceRefresh && currentBoard && currentBoard.id === id) {
      return;
    }

    set({ isLoading: true, error: null });
    try {
      const response = await api.get(`/boards/${id}`);
      set({ currentBoard: response.data, isLoading: false });
    } catch (error: unknown) {
      console.error('Fetch board error:', error); // Added logging
      set({ error: extractError(error, 'Failed to fetch board'), isLoading: false });
    }
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createBoard: async (boardData: any, userId) => {
    set({ isLoading: true, error: null });
    try {
      await api.post('/boards/', boardData, {
        params: { user_id: userId } // In real app, userId comes from token
      });
      const { currentUserId, currentSearchQuery } = get();
      await get().fetchBoards(currentUserId, currentSearchQuery, true, 1);
    } catch (error: unknown) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (typeof error === 'object' && error && (error as any).message === 'offline') {
        // Offline handling logic if needed
      }
      set({ error: extractError(error, 'Failed to create board'), isLoading: false });
      throw error;
    }
  },

  updateBoard: async (id, boardData) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.put(`/boards/${id}`, boardData);
      set((state) => ({
        boards: state.boards.map(b => b.id === id ? response.data : b),
        currentBoard: state.currentBoard?.id === id ? response.data : state.currentBoard,
        isLoading: false
      }));
    } catch (error: unknown) {
      set({ error: extractError(error, 'Failed to update board'), isLoading: false });
      throw error;
    }
  },

  deleteBoard: async (id, skipRefresh = false) => {
    set({ isLoading: true, error: null });
    try {
      await api.delete(`/boards/${id}`);
      
      if (skipRefresh) {
        set((state) => ({
          boards: state.boards.filter(b => b.id !== id),
          currentBoard: state.currentBoard?.id === id ? null : state.currentBoard,
          isLoading: false
        }));
      } else {
        const { currentUserId, currentSearchQuery } = get();
        // Always refresh page 1 to handle pagination gaps correctly
        await get().fetchBoards(currentUserId, currentSearchQuery, true, 1);
      }
    } catch (error: unknown) {
      set({ error: extractError(error, 'Failed to delete board'), isLoading: false });
      throw error;
    }
  },

  duplicateBoard: async (id, userId) => {
    set({ isLoading: true, error: null });
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
      set({ isLoading: false });
    } catch (e: unknown) {
      set({ error: extractError(e, 'Failed to duplicate board'), isLoading: false });
      throw e;
    }
  },

  fetchAssignedBoards: async (studentId, forceRefresh = false) => {
    const { lastFetchTime, assignedBoards } = get();
    const now = Date.now();
    if (!forceRefresh && lastFetchTime && assignedBoards.length > 0 && (now - lastFetchTime) < CACHE_DURATION) {
      return;
    }
    set({ isLoading: true, error: null });
    try {
      const response = await api.get('/boards/assigned', { params: { student_id: studentId } });
      set({ assignedBoards: response.data, isLoading: false, lastFetchTime: now });
    } catch (error: unknown) {
      set({ error: extractError(error, 'Failed to fetch assigned boards'), isLoading: false });
    }
  },

  addSymbolToBoard: async (boardId, symbolId, position) => {
    set({ isLoading: true, error: null });
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
          },
          isLoading: false
        });
      } else {
        set({ isLoading: false });
      }
      return response.data;
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to add symbol';
        }
        return 'Failed to add symbol';
      })();
      set({ error: detail, isLoading: false });
      throw error;
    }
  },

  updateBoardSymbol: async (boardId, symbolId, updates) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.put(`/boards/${boardId}/symbols/${symbolId}`, updates);
      
      // Update current board symbols
      const currentBoard = get().currentBoard;
      if (currentBoard && currentBoard.id === boardId) {
        set({
          currentBoard: {
            ...currentBoard,
            symbols: currentBoard.symbols.map(s => s.id === symbolId ? response.data : s)
          },
          isLoading: false
        });
      } else {
        set({ isLoading: false });
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to update symbol';
        }
        return 'Failed to update symbol';
      })();
      set({ error: detail, isLoading: false });
      throw error;
    }
  },

  deleteBoardSymbol: async (boardId, symbolId) => {
    set({ isLoading: true, error: null });
    try {
      await api.delete(`/boards/${boardId}/symbols/${symbolId}`);
      
      // Update current board symbols
      const currentBoard = get().currentBoard;
      if (currentBoard && currentBoard.id === boardId) {
        set({
          currentBoard: {
            ...currentBoard,
            symbols: currentBoard.symbols.filter(s => s.id !== symbolId)
          },
          isLoading: false
        });
      } else {
        set({ isLoading: false });
      }
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to delete symbol';
        }
        return 'Failed to delete symbol';
      })();
      set({ error: detail, isLoading: false });
      throw error;
    }
  },

  batchUpdateSymbols: async (boardId, updates) => {
    set({ isLoading: true, error: null });
    try {
      await api.put(`/boards/${boardId}/symbols/batch`, updates);
      
      // Refresh the board to get updated symbols
      await get().fetchBoard(boardId, true);
      set({ isLoading: false });
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to batch update symbols';
        }
        return 'Failed to batch update symbols';
      })();
      set({ error: detail, isLoading: false });
      throw error;
    }
  },

  assignBoardToStudent: async (boardId, studentId, assignedBy) => {
    set({ isLoading: true, error: null });
    try {
      await api.post(`/boards/${boardId}/assign`, {
        student_id: studentId,
        assigned_by: assignedBy
      });
      try {
        useNotificationsStore.getState().add({ title: 'Board assigned', message: `Board ${boardId} assigned to student ${studentId}` })
      } catch { /* notification optional */ }
      set({ isLoading: false });
    } catch (e: unknown) {
      const detail = (() => {
        if (typeof e === 'object' && e && 'response' in e) {
          const r = e as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to assign board';
        }
        return 'Failed to assign board';
      })();
      set({ error: detail, isLoading: false });
      throw e;
    }
  }
  ,
  unassignBoardFromStudent: async (boardId, studentId) => {
    set({ isLoading: true, error: null });
    try {
      await api.delete(`/boards/${boardId}/assign/${studentId}`);
      try {
        useNotificationsStore.getState().add({ title: 'Board unassigned', message: `Board ${boardId} unassigned from student ${studentId}` })
      } catch { /* notification optional */ }
      set({ isLoading: false });
    } catch (e: unknown) {
      const detail = (() => {
        if (typeof e === 'object' && e && 'response' in e) {
          const r = e as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to unassign board';
        }
        return 'Failed to unassign board';
      })();
      set({ error: detail, isLoading: false });
      throw e;
    }
  }
}));
