import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Board, BoardSymbol } from '../src/types';

const hoisted = vi.hoisted(() => {
  const board = {
    currentBoard: null as Board | null,
    isBoardLoading: false,
    error: null as string | null,
    fetchBoard: vi.fn(),
    addSymbolToBoard: vi.fn(),
    batchUpdateSymbols: vi.fn(),
    updateBoard: vi.fn(),
    deleteBoardSymbol: vi.fn(),
  };
  const auth = {
    user: { id: 1, username: 'admin1', user_type: 'admin' as const },
    token: 'test-token',
  };
  const settings = {
    aiSettings: {
      provider: 'openrouter',
      openrouter_model: 'model-1',
      lmstudio_model: undefined,
      ollama_model: undefined,
    } as Record<string, unknown> | null,
    fetchAISettings: vi.fn(),
  };
  const toast = { addToast: vi.fn() };
  const editorSymbols = {
    localSymbols: [] as BoardSymbol[],
    activeSymbol: null as BoardSymbol | null,
    editingSymbol: null as BoardSymbol | null,
    hasChanges: false,
    setHasChanges: vi.fn(),
    setEditingSymbol: vi.fn(),
    clearOverrides: vi.fn(),
    handleRemoteMove: vi.fn(),
    handleDragStart: vi.fn(),
    handleDragEnd: vi.fn(),
    handleUpdateSymbol: vi.fn(),
  };
  const ai = {
    aiSuggestions: [] as unknown[],
    aiLoading: false,
    aiError: null as string | null,
    applyId: null as number | null,
    refinePrompt: '',
    applyAllLoading: false,
    setAiError: vi.fn(),
    setRefinePrompt: vi.fn(),
    loadAISuggestions: vi.fn(),
    handleRefine: vi.fn(),
    handleRegenerate: vi.fn(),
    applySuggestion: vi.fn(),
    applyAllSuggestions: vi.fn(),
  };
  const navigate = vi.fn();
  return { board, auth, settings, toast, editorSymbols, ai, navigate };
});

vi.mock('../src/store/boardStore', () => {
  const useBoardStore = (selector?: (value: typeof hoisted.board) => unknown) =>
    selector ? selector(hoisted.board) : hoisted.board;
  return { useBoardStore };
});

vi.mock('../src/store/authStore', () => {
  const useAuthStore = (selector?: (value: typeof hoisted.auth) => unknown) =>
    selector ? selector(hoisted.auth) : hoisted.auth;
  return { useAuthStore };
});

vi.mock('../src/store/settingsStore', () => {
  const useSettingsStore = (selector?: (value: typeof hoisted.settings) => unknown) =>
    selector ? selector(hoisted.settings) : hoisted.settings;
  return { useSettingsStore };
});

vi.mock('../src/store/toastStore', () => ({
  useToastStore: (selector?: (s: { addToast: typeof hoisted.toast.addToast }) => unknown) => {
    const state = { addToast: hoisted.toast.addToast };
    return selector ? selector(state) : state;
  },
}));

vi.mock('../src/lib/api', () => ({
  extractError: (_e: unknown, fallback: string) => fallback,
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../src/hooks/useBoardEditorSymbols', () => ({
  useBoardEditorSymbols: () => hoisted.editorSymbols,
}));

vi.mock('../src/hooks/useBoardCollab', () => ({
  useBoardCollab: () => ({ sendMove: vi.fn() }),
}));

vi.mock('../src/hooks/useBoardAISuggestions', () => ({
  useBoardAISuggestions: () => hoisted.ai,
}));

vi.mock('react-router', () => ({
  useParams: () => ({ id: '1' }),
  useNavigate: () => hoisted.navigate,
}));

const stableT = vi.hoisted(() => vi.fn((key: string, fallback?: string) => fallback ?? key));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}));

vi.mock('../src/components/board/BoardEditorToolbar', () => ({
  BoardEditorToolbar: ({ onLoadSuggestions, onSpeakMode, onOpenSettings, onGridChange, onSave, onClear }: {
    onLoadSuggestions: () => void;
    onSpeakMode: () => void;
    onOpenSettings: () => void;
    onGridChange: (p: string) => void;
    onSave: () => void;
    onClear: () => void;
  }) => (
    <div>
      <button onClick={onLoadSuggestions}>load-suggestions</button>
      <button onClick={onSpeakMode}>speak-mode</button>
      <button onClick={onOpenSettings}>open-settings</button>
      <button onClick={() => onGridChange('3x3')}>grid-change</button>
      <button onClick={onSave}>save-layout</button>
      <button onClick={onClear}>clear-board</button>
    </div>
  ),
}));

vi.mock('../src/components/board/BoardEditorGrid', () => ({
  BoardEditorGrid: ({ onAddSymbol, onRemoveSymbol, onEditSymbol, onDragStart, onDragEnd }: {
    onAddSymbol: (x: number, y: number) => void;
    onRemoveSymbol: (id: number) => void;
    onEditSymbol: (s: BoardSymbol) => void;
    onDragStart: (e: unknown) => void;
    onDragEnd: (e: unknown) => void;
  }) => (
    <div>
      <button onClick={() => onAddSymbol(1, 2)}>add-symbol</button>
      <button onClick={() => onRemoveSymbol(99)}>remove-symbol</button>
      <button onClick={() => onEditSymbol(makeSymbol(9, 'edit'))}>edit-symbol</button>
      <button onClick={() => onDragStart({ active: { id: 'a', data: { current: makeSymbol(1, 'drag') } } })}>
        drag-start
      </button>
      <button onClick={() => onDragEnd({
        active: { id: 'a', data: { current: makeSymbol(1, 'drag') } },
        over: { id: 'b', data: { current: { x: 2, y: 3 } } },
      })}>
        drag-end
      </button>
    </div>
  ),
}));

vi.mock('../src/components/board/SymbolPicker', () => ({
  SymbolPicker: ({ isOpen, onSelect, onClose }: { isOpen: boolean; onSelect: (id: number) => void; onClose: () => void }) => (
    <div>
      {isOpen && <span>picker-open</span>}
      <button onClick={() => onSelect(77)}>pick-symbol</button>
      <button onClick={onClose}>picker-close</button>
    </div>
  ),
}));

vi.mock('../src/components/board/SymbolEditorDialog', () => ({
  SymbolEditorDialog: ({ isOpen, onSave, onClose }: { isOpen: boolean; onSave: (s: unknown) => void; onClose: () => void }) => (
    <div>
      {isOpen && <span>editor-open</span>}
      <button onClick={() => onSave(makeSymbol(9, 'edit'))}>editor-save</button>
      <button onClick={onClose}>editor-close</button>
    </div>
  ),
}));

vi.mock('../src/components/board/BoardSettingsDialog', () => ({
  BoardSettingsDialog: ({ onSave, onClose, onBoardNameChange, onAiEnabledChange, saveSuccess, aiConfigError }: {
    onSave: () => void;
    onClose: () => void;
    onBoardNameChange: (n: string) => void;
    onAiEnabledChange: (v: boolean) => void;
    saveSuccess: boolean;
    aiConfigError: string | null;
  }) => (
    <div>
      {saveSuccess && <span>save-success</span>}
      {aiConfigError && <span>config-error:{aiConfigError}</span>}
      <button onClick={onSave}>settings-save</button>
      <button onClick={onClose}>settings-close</button>
      <button onClick={() => onBoardNameChange('Renamed Board')}>name-change</button>
      <button onClick={() => onAiEnabledChange(true)}>ai-enable</button>
    </div>
  ),
}));

vi.mock('../src/components/board/AISuggestionPanel', () => ({
  AISuggestionPanel: ({ onRefresh }: { onRefresh: () => void }) => (
    <div data-testid="ai-panel">
      <button onClick={onRefresh}>ai-refresh</button>
    </div>
  ),
}));

vi.mock('../src/components/ui/LoadingState', () => ({
  LoadingState: () => <div>loading-state</div>,
}));

vi.mock('../src/components/ui/ConfirmDialog', () => ({
  ConfirmDialog: ({ isOpen, onConfirm, onClose }: { isOpen: boolean; onConfirm: () => void; onClose: () => void }) => (
    <div>
      {isOpen && <span>confirm-open</span>}
      <button onClick={onConfirm}>confirm-clear</button>
      <button onClick={onClose}>confirm-close</button>
    </div>
  ),
}));

import { BoardEditor } from '../src/pages/BoardEditor';

function makeSymbol(id: number, label: string, overrides: Partial<BoardSymbol> = {}): BoardSymbol {
  return {
    id,
    symbol_id: id,
    position_x: 0,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: { id, label, category: 'core' },
    ...overrides,
  };
}

function makeBoard(overrides: Partial<Board> = {}): Board {
  return {
    id: 1,
    user_id: 1,
    name: 'My Board',
    description: 'A test board',
    category: 'general',
    is_public: false,
    is_template: false,
    created_at: '',
    updated_at: '',
    symbols: [makeSymbol(1, 'Apple'), makeSymbol(2, 'Banana')],
    grid_rows: 4,
    grid_cols: 5,
    ai_enabled: false,
    ...overrides,
  };
}

function renderEditor() {
  return render(<BoardEditor />);
}

describe('BoardEditor page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hoisted.board.currentBoard = makeBoard();
    hoisted.board.isBoardLoading = false;
    hoisted.board.error = null;
    hoisted.auth.user = { id: 1, username: 'admin1', user_type: 'admin' };
    hoisted.auth.token = 'test-token';
    hoisted.settings.aiSettings = {
      provider: 'openrouter',
      openrouter_model: 'model-1',
      lmstudio_model: undefined,
      ollama_model: undefined,
    };
    hoisted.editorSymbols.localSymbols = [];
    hoisted.editorSymbols.hasChanges = false;
    hoisted.ai.aiSuggestions = [];
    hoisted.ai.aiError = null;
    hoisted.board.fetchBoard.mockResolvedValue({});
    hoisted.board.batchUpdateSymbols.mockResolvedValue({});
    hoisted.board.updateBoard.mockResolvedValue({});
    hoisted.board.deleteBoardSymbol.mockResolvedValue({});
    hoisted.board.addSymbolToBoard.mockResolvedValue({});
    hoisted.settings.fetchAISettings.mockResolvedValue({});
  });

  it('shows a loading state while the board is being fetched', () => {
    hoisted.board.isBoardLoading = true;
    hoisted.board.currentBoard = null;
    renderEditor();
    expect(screen.getByText('loading-state')).toBeInTheDocument();
  });

  it('shows the error state when the fetch failed', () => {
    hoisted.board.error = 'Fetch failed';
    hoisted.board.currentBoard = null;
    renderEditor();
    expect(screen.getByText('Fetch failed')).toBeInTheDocument();
  });

  it('shows the not-found message when there is no board', () => {
    hoisted.board.currentBoard = null;
    renderEditor();
    expect(screen.getByText('boardNotFound')).toBeInTheDocument();
  });

  it('fetches the board and AI settings on mount', () => {
    hoisted.settings.aiSettings = null;
    renderEditor();
    expect(hoisted.board.fetchBoard).toHaveBeenCalledWith(1);
    expect(hoisted.settings.fetchAISettings).toHaveBeenCalled();
  });

  it('saves the layout and shows a success toast', async () => {
    hoisted.editorSymbols.hasChanges = true;
    hoisted.editorSymbols.localSymbols = [makeSymbol(1, 'Apple', { position_x: 1, position_y: 2 })];
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'save-layout' }));

    await waitFor(() => {
      expect(hoisted.board.batchUpdateSymbols).toHaveBeenCalledWith(
        1,
        expect.arrayContaining([expect.objectContaining({ id: 1, position_x: 1, position_y: 2 })]),
      );
      expect(hoisted.toast.addToast).toHaveBeenCalledWith('layoutSaved', 'success');
    });
    expect(hoisted.editorSymbols.clearOverrides).toHaveBeenCalled();
  });

  it('shows an error toast when saving the layout fails', async () => {
    hoisted.editorSymbols.hasChanges = true;
    hoisted.board.batchUpdateSymbols.mockRejectedValue(new Error('boom'));
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'save-layout' }));

    await waitFor(() => {
      expect(hoisted.toast.addToast).toHaveBeenCalledWith('layoutSaveFailed', 'error');
    });
  });

  it('updates the grid and reverts on failure', async () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'grid-change' }));
    await waitFor(() => {
      expect(hoisted.board.updateBoard).toHaveBeenCalledWith(1, { grid_rows: 3, grid_cols: 3 });
    });

    hoisted.board.updateBoard.mockRejectedValue(new Error('grid fail'));
    fireEvent.click(screen.getByRole('button', { name: 'grid-change' }));
    await waitFor(() => {
      expect(hoisted.toast.addToast).toHaveBeenCalledWith('settingsSaveFailed', 'error');
    });
  });

  it('adds a symbol at the selected position', async () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'add-symbol' }));
    fireEvent.click(screen.getByRole('button', { name: 'pick-symbol' }));

    await waitFor(() => {
      expect(hoisted.board.addSymbolToBoard).toHaveBeenCalledWith(1, 77, { x: 1, y: 2 });
    });
  });

  it('removes a symbol and refreshes the board', async () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'remove-symbol' }));

    await waitFor(() => {
      expect(hoisted.board.deleteBoardSymbol).toHaveBeenCalledWith(1, 99);
      expect(hoisted.board.fetchBoard).toHaveBeenCalled();
    });
  });

  it('reports a remove error through the AI error surface', async () => {
    hoisted.board.deleteBoardSymbol.mockRejectedValue(new Error('remove fail'));
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'remove-symbol' }));

    await waitFor(() => {
      expect(hoisted.ai.setAiError).toHaveBeenCalledWith('failedToRemoveSymbol');
    });
  });

  it('clears the board by deleting every symbol', async () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'clear-board' }));
    fireEvent.click(screen.getByRole('button', { name: 'confirm-clear' }));

    await waitFor(() => {
      expect(hoisted.board.deleteBoardSymbol).toHaveBeenCalledTimes(2);
      expect(hoisted.board.fetchBoard).toHaveBeenCalled();
    });
  });

  it('reports a clear error through the AI error surface', async () => {
    hoisted.board.deleteBoardSymbol.mockRejectedValue(new Error('clear fail'));
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'clear-board' }));
    fireEvent.click(screen.getByRole('button', { name: 'confirm-clear' }));

    await waitFor(() => {
      expect(hoisted.ai.setAiError).toHaveBeenCalledWith('failedToClearBoard');
    });
  });

  it('saves board settings with the resolved AI provider', async () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'open-settings' }));
    fireEvent.click(screen.getByRole('button', { name: 'ai-enable' }));
    fireEvent.click(screen.getByRole('button', { name: 'name-change' }));
    fireEvent.click(screen.getByRole('button', { name: 'settings-save' }));

    await waitFor(() => {
      expect(hoisted.board.updateBoard).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          name: 'Renamed Board',
          ai_enabled: true,
          ai_provider: 'openrouter',
          ai_model: '@primary',
        }),
      );
    });
    expect(screen.getByText('save-success')).toBeInTheDocument();
  });

  it('flags incomplete AI config when enabling AI without a provider', async () => {
    hoisted.settings.aiSettings = null;
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'open-settings' }));
    fireEvent.click(screen.getByRole('button', { name: 'ai-enable' }));
    fireEvent.click(screen.getByRole('button', { name: 'settings-save' }));

    await waitFor(() => {
      expect(hoisted.board.updateBoard).not.toHaveBeenCalled();
    });
    expect(screen.getByText('config-error:aiConfigIncomplete')).toBeInTheDocument();
  });

  it('navigates to speak mode and drives drag handlers', () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'speak-mode' }));
    expect(hoisted.navigate).toHaveBeenCalledWith('/play/1');

    fireEvent.click(screen.getByRole('button', { name: 'drag-start' }));
    expect(hoisted.editorSymbols.handleDragStart).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'drag-end' }));
    expect(hoisted.editorSymbols.handleDragEnd).toHaveBeenCalled();
  });

  it('renders the AI panel when suggestions exist', () => {
    hoisted.board.currentBoard = makeBoard({ ai_enabled: true });
    hoisted.ai.aiSuggestions = [{}];
    renderEditor();
    expect(screen.getByTestId('ai-panel')).toBeInTheDocument();
  });

  it('replaces an existing symbol before adding at the same position', async () => {
    hoisted.editorSymbols.localSymbols = [makeSymbol(1, 'Apple', { position_x: 1, position_y: 2 })];
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'add-symbol' }));
    fireEvent.click(screen.getByRole('button', { name: 'pick-symbol' }));

    await waitFor(() => {
      expect(hoisted.board.deleteBoardSymbol).toHaveBeenCalledWith(1, 1);
      expect(hoisted.board.addSymbolToBoard).toHaveBeenCalledWith(1, 77, { x: 1, y: 2 });
    });
  });

  it('logs a failure when adding a symbol fails', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    hoisted.board.addSymbolToBoard.mockRejectedValue(new Error('add fail'));
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'add-symbol' }));
    fireEvent.click(screen.getByRole('button', { name: 'pick-symbol' }));

    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
    spy.mockRestore();
  });

  it('shows an error toast when saving settings fails', async () => {
    hoisted.board.updateBoard.mockRejectedValue(new Error('settings fail'));
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'open-settings' }));
    fireEvent.click(screen.getByRole('button', { name: 'settings-save' }));

    await waitFor(() => {
      expect(hoisted.toast.addToast).toHaveBeenCalledWith('settingsSaveFailed', 'error');
    });
  });

  it('closes the settings dialog after the success timer elapses', async () => {
    vi.useFakeTimers();
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'open-settings' }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'settings-save' }));
    });
    expect(screen.getByText('save-success')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.queryByText('save-success')).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it('clears the previous success timer when saving settings again', async () => {
    vi.useFakeTimers();
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'open-settings' }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'settings-save' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'settings-save' }));
    });

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.queryByText('save-success')).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it('closes the picker, editor, confirm and settings dialogs', () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'add-symbol' }));
    expect(screen.getByText('picker-open')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'picker-close' }));
    expect(screen.queryByText('picker-open')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'clear-board' }));
    expect(screen.getByText('confirm-open')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'confirm-close' }));
    expect(screen.queryByText('confirm-open')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'settings-close' }));
  });

  it('does nothing on save with no pending changes', async () => {
    hoisted.editorSymbols.hasChanges = false;
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'save-layout' }));
    await new Promise((r) => setTimeout(r, 20));
    expect(hoisted.board.batchUpdateSymbols).not.toHaveBeenCalled();
  });

  it('does nothing on clear when the board has no symbols', async () => {
    hoisted.board.currentBoard = makeBoard({ symbols: [] });
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'clear-board' }));
    fireEvent.click(screen.getByRole('button', { name: 'confirm-clear' }));
    await new Promise((r) => setTimeout(r, 20));
    expect(hoisted.board.deleteBoardSymbol).not.toHaveBeenCalled();
  });

  it('loads AI suggestions from the toolbar and refreshes from the panel', () => {
    hoisted.board.currentBoard = makeBoard({ ai_enabled: true });
    hoisted.ai.aiSuggestions = [{}];
    renderEditor();

    fireEvent.click(screen.getByRole('button', { name: 'load-suggestions' }));
    expect(hoisted.ai.loadAISuggestions).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'ai-refresh' }));
    expect(hoisted.ai.loadAISuggestions).toHaveBeenCalledTimes(2);
  });
});
