import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';

import { Boards } from '../src/pages/Boards';
import { useBoardStore } from '../src/store/boardStore';
import { useAuthStore } from '../src/store/authStore';
import { useSettingsStore } from '../src/store/settingsStore';
import api from '../src/lib/api';
import i18n from '../src/i18n/index';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  apiOffline: { isOffline: () => false },
  extractError: (error: unknown, fallback: string) => {
    const value = error as { message?: string };
    return value.message || fallback;
  },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('../src/store/settingsStore', () => ({
  useSettingsStore: vi.fn(),
}));

vi.mock('../src/lib/format', () => ({
  formatDate: (value: string) => `date:${value}`,
}));

const tFn = (key: string, defaultValue?: string | { defaultValue?: string }) => {
  const values: Record<string, string> = {
    title: 'Communication Boards',
    subtitle: 'Manage your communication boards',
    searchPlaceholder: 'Search boards...',
    newBoard: 'New Board',
    createTitle: 'Create New Board',
    boardName: 'Board Name',
    description: 'Description',
    placeholderName: 'e.g., Daily Activities',
    optionalDescription: 'Optional description',
    languageLearning: 'Language Learning Board',
    languageLearningDesc: 'Symbols will always be displayed in their original language.',
    enableAI: 'Enable AI-Powered Symbol Suggestions',
    aiSettingsMissing: 'AI settings are missing a configured provider/model. Update them in Settings first.',
    cancel: 'Cancel',
    create: 'Create Board',
    refresh: 'Refresh',
    selectAll: 'Select All',
    deleteSelected: 'Delete Selected',
    delete: 'Delete',
    deleteBoardTitle: 'Delete Board',
    deleteConfirm: 'Are you sure you want to delete this board?',
    bulkDeleteTitle: 'Delete Selected Boards',
    bulkDeleteConfirm: 'Are you sure you want to delete the selected boards?',
    duplicateBoard: 'Duplicate board',
    assignToStudent: 'Assign to student',
    assignToStudentTitle: 'Assign to Student',
    close: 'Close',
    assign: 'Assign',
    loadStudentsError: 'Failed to load students',
    assignBoardError: 'Failed to assign board',
    loadMore: 'Load More',
    retry: 'Retry',
    bulkDeleteFailed: 'Some boards could not be deleted. The failed boards remain selected.',
  };
  if (values[key]) return values[key];
  if (typeof defaultValue === 'string') return defaultValue;
  return defaultValue?.defaultValue ?? key;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: tFn,
    i18n: { language: 'en' },
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
}));

// The store's duplicateBoard reads the real i18n module (not the mocked
// useTranslation hook above), so compute the localized suffix the same way.
const copySuffix = i18n.t('boards:copySuffix', ' (Copy)');

describe('Boards page management', () => {
  const board = {
    id: 1,
    user_id: 10,
    name: 'Morning Routine',
    description: 'Daily steps',
    category: 'general',
    is_public: false,
    is_template: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    symbols: [],
  };

  const teacher = {
    id: 10,
    username: 'teacher1',
    display_name: 'Teacher',
    user_type: 'teacher' as const,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  };

  const studentUser = {
    id: 20,
    username: 'student1',
    display_name: 'Leo',
    user_type: 'student' as const,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  };

  const aiSettings = {
    provider: 'openrouter',
    openrouter_model: 'gpt-4o-mini',
    lmstudio_model: null,
    ollama_model: null,
  };

  const admin = {
    id: 99,
    username: 'admin',
    display_name: 'Admin',
    user_type: 'admin' as const,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useBoardStore.setState({
      boards: [],
      assignedBoards: [],
      isLoading: false,
      isListLoading: false,
      isBoardLoading: false,
      error: null,
      lastFetchTime: null,
      hasMore: false,
      page: 1,
    });
    vi.mocked(useAuthStore).mockImplementation(
      (selector?: (state: { user: typeof teacher }) => unknown) =>
        selector ? selector({ user: teacher }) : { user: teacher },
    );
    vi.mocked(useSettingsStore).mockImplementation(
      (selector?: (state: { aiSettings: typeof aiSettings | null; fetchAISettings: ReturnType<typeof vi.fn> }) => unknown) =>
        selector
          ? selector({ aiSettings: null, fetchAISettings: vi.fn().mockResolvedValue(undefined) })
          : { aiSettings: null, fetchAISettings: vi.fn().mockResolvedValue(undefined) },
    );
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    vi.mocked(api.delete).mockResolvedValue({ data: {} });
  });

  const renderBoards = () =>
    render(
      <MemoryRouter>
        <Boards />
      </MemoryRouter>,
    );

  const mockBoardList = (...boards: typeof board[]) => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: boards });
      return Promise.resolve({ data: [] });
    });
  };

  it('shows a spinner while the board list is loading', async () => {
    useBoardStore.setState({ isListLoading: true });
    renderBoards();

    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
  });

  it('creates a board with the given name and description', async () => {
    renderBoards();
    await screen.findByText('Communication Boards');

    fireEvent.click(screen.getByText('New Board'));
    fireEvent.change(screen.getByLabelText('Board Name'), { target: { value: 'Colors' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Learn colors' } });
    fireEvent.click(screen.getByText('Create Board'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/boards/',
        {
          name: 'Colors',
          description: 'Learn colors',
          category: 'general',
          is_public: false,
          is_template: false,
          ai_enabled: false,
          ai_provider: undefined,
          ai_model: undefined,
          locale: 'en',
          is_language_learning: false,
        },
        { params: { user_id: 10 } },
      ),
    );
  });

  it('creates a language-learning board with AI configured', async () => {
    vi.mocked(useSettingsStore).mockImplementation(
      (selector?: (state: { aiSettings: typeof aiSettings; fetchAISettings: ReturnType<typeof vi.fn> }) => unknown) =>
        selector
          ? selector({ aiSettings, fetchAISettings: vi.fn().mockResolvedValue(undefined) })
          : { aiSettings, fetchAISettings: vi.fn().mockResolvedValue(undefined) },
    );
    renderBoards();
    await screen.findByText('Communication Boards');

    fireEvent.click(screen.getByText('New Board'));
    fireEvent.change(screen.getByLabelText('Board Name'), { target: { value: 'Bilingual' } });
    fireEvent.click(screen.getByLabelText('Language Learning Board'));
    fireEvent.click(screen.getByLabelText('Enable AI-Powered Symbol Suggestions'));
    await screen.findByText('openrouter - gpt-4o-mini');
    fireEvent.click(screen.getByText('Create Board'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/boards/',
        {
          name: 'Bilingual',
          description: '',
          category: 'general',
          is_public: false,
          is_template: false,
          ai_enabled: true,
          ai_provider: 'openrouter',
          ai_model: 'gpt-4o-mini',
          locale: 'en',
          is_language_learning: true,
        },
        { params: { user_id: 10 } },
      ),
    );
  });

  it('blocks AI-enabled creation when no provider is configured', async () => {
    renderBoards();
    await screen.findByText('Communication Boards');

    fireEvent.click(screen.getByText('New Board'));
    fireEvent.change(screen.getByLabelText('Board Name'), { target: { value: 'AI Board' } });
    fireEvent.click(screen.getByLabelText('Enable AI-Powered Symbol Suggestions'));

    expect(
      await screen.findByText('AI settings are missing a configured provider/model. Update them in Settings first.'),
    ).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('deletes a board after confirmation', async () => {
    mockBoardList(board);
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Delete'));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByText('Delete'));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/boards/1'));
  });

  it('duplicates a board including its symbols', async () => {
    mockBoardList(board);
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: [board] });
      if (url === '/boards/1') {
        return Promise.resolve({
          data: {
            ...board,
            symbols: [
              { symbol: { id: 5 }, position_x: 0, position_y: 0, size: 1, is_visible: true, custom_text: null },
            ],
          },
        });
      }
      return Promise.resolve({ data: [] });
    });
    vi.mocked(api.post).mockResolvedValue({ data: { id: 99 } });
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Duplicate board'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/boards/',
        {
          name: `Morning Routine${copySuffix}`,
          description: 'Daily steps',
          category: 'general',
          is_public: false,
          is_template: false,
          grid_rows: 4,
          grid_cols: 5,
          locale: 'en',
          is_language_learning: false,
          ai_enabled: false,
        },
        { params: { user_id: 10 } },
      ),
    );
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/boards/99/symbols', {
        symbol_id: 5,
        position_x: 0,
        position_y: 0,
        size: 1,
        is_visible: true,
        custom_text: null,
        color: null,
        linked_board_id: null,
      }),
    );
  });

  it('duplicates a board preserving grid, language flag, symbol color, folder links and AI config', async () => {
    const source = {
      ...board,
      grid_rows: 3,
      grid_cols: 6,
      locale: 'es',
      is_language_learning: true,
      ai_enabled: true,
      ai_provider: 'openrouter',
      ai_model: 'gpt-4o-mini',
    };
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: [source] });
      if (url === '/boards/1') {
        return Promise.resolve({
          data: {
            ...source,
            symbols: [
              {
                symbol: { id: 5 },
                position_x: 2,
                position_y: 1,
                size: 2,
                is_visible: true,
                custom_text: 'Mi vaca',
                color: '#fee2e2',
                linked_board_id: 7,
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: [] });
    });
    vi.mocked(api.post).mockResolvedValue({ data: { id: 99 } });
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Duplicate board'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/boards/',
        {
          name: `Morning Routine${copySuffix}`,
          description: 'Daily steps',
          category: 'general',
          is_public: false,
          is_template: false,
          grid_rows: 3,
          grid_cols: 6,
          locale: 'es',
          is_language_learning: true,
          ai_enabled: false,
        },
        { params: { user_id: 10 } },
      ),
    );
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/boards/99/symbols', {
        symbol_id: 5,
        position_x: 2,
        position_y: 1,
        size: 2,
        is_visible: true,
        custom_text: 'Mi vaca',
        color: '#fee2e2',
        linked_board_id: 7,
      }),
    );
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/boards/99', {
        ai_enabled: true,
        ai_provider: 'openrouter',
        ai_model: 'gpt-4o-mini',
      }),
    );
  });

  it('assigns a board to a selected student', async () => {
    mockBoardList(board);
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: [board] });
      if (url === '/auth/users') return Promise.resolve({ data: [studentUser, teacher] });
      return Promise.resolve({ data: [] });
    });
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Assign to student'));
    const select = await screen.findByRole('combobox');
    fireEvent.pointerDown(select, { button: 0, ctrlKey: false });
    fireEvent.click(select);
    const leoOption = await screen.findByRole('option', { name: 'Leo' });
    fireEvent.pointerDown(leoOption, { button: 0, ctrlKey: false });
    fireEvent.click(leoOption);
    fireEvent.click(screen.getByText('Assign'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/boards/1/assign', {
        student_id: 20,
        assigned_by: 10,
      }),
    );
  });

  it('selects all boards and bulk-deletes them, reporting failures', async () => {
    const second = { ...board, id: 2, name: 'Evening Routine' };
    mockBoardList(board, second);
    vi.mocked(api.delete)
      .mockResolvedValueOnce({ data: {} })
      .mockRejectedValueOnce({ response: { status: 500 } });
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Select All'));
    fireEvent.click(screen.getByRole('button', { name: /Delete Selected/ }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByText('Delete'));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/boards/1'));
    expect(api.delete).toHaveBeenCalledWith('/boards/2');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('refreshes the list and loads more pages', async () => {
    const many = Array.from({ length: 100 }, (_, i) => ({ ...board, id: i + 1, name: `Board ${i + 1}` }));
    mockBoardList(...many);
    useBoardStore.setState({ boards: [board], isListLoading: false, hasMore: true, page: 1 });
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByTestId('force-refresh'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/boards/', {
        params: { user_id: 10, skip: 0, limit: 100 },
      }),
    );

    fireEvent.click(screen.getByText('Load More'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/boards/', {
        params: { user_id: 10, skip: 100, limit: 100 },
      }),
    );
  }, 20000);

  it('shows the error banner and retries', async () => {
    vi.mocked(api.get)
      .mockRejectedValueOnce(new Error('server exploded'))
      .mockResolvedValue({ data: [] });
    renderBoards();

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('server exploded')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Retry'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/boards/', {
        params: { user_id: 10, skip: 0, limit: 100 },
      }),
    );
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('searches boards as admin without scoping to a user id', async () => {
    vi.mocked(useAuthStore).mockImplementation(
      (selector?: (state: { user: typeof admin }) => unknown) =>
        selector ? selector({ user: admin }) : { user: admin },
    );
    renderBoards();
    await screen.findByText('Communication Boards');

    fireEvent.change(screen.getByLabelText('Search boards...'), { target: { value: 'morn' } });

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/boards/', {
        params: expect.objectContaining({ name: 'morn' }),
      }),
    );
  });

  it('does not fetch or refresh when no user is present', async () => {
    vi.mocked(useAuthStore).mockImplementation(
      (selector?: (state: { user: null }) => unknown) =>
        selector ? selector({ user: null }) : { user: null },
    );
    renderBoards();

    expect(api.get).not.toHaveBeenCalled();
  });

  it('shows an error when loading students fails', async () => {
    mockBoardList(board);
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: [board] });
      if (url === '/auth/users') return Promise.reject(new Error('load fail'));
      return Promise.resolve({ data: [] });
    });
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Assign to student'));

    expect(await screen.findByText('Failed to load students')).toBeInTheDocument();
  });

  it('shows an error when assigning a board fails', async () => {
    mockBoardList(board);
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: [board] });
      if (url === '/auth/users') return Promise.resolve({ data: [studentUser, teacher] });
      return Promise.resolve({ data: [] });
    });
    vi.mocked(api.post).mockRejectedValue(new Error('assign fail'));
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Assign to student'));
    const select = await screen.findByRole('combobox');
    fireEvent.pointerDown(select, { button: 0, ctrlKey: false });
    fireEvent.click(select);
    const leoOption = await screen.findByRole('option', { name: 'Leo' });
    fireEvent.pointerDown(leoOption, { button: 0, ctrlKey: false });
    fireEvent.click(leoOption);
    fireEvent.click(screen.getByText('Assign'));

    expect(await screen.findByText('Failed to assign board')).toBeInTheDocument();
  });

  it('cancels the create form and closes the assign panel', async () => {
    mockBoardList(board);
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: [board] });
      if (url === '/auth/users') return Promise.resolve({ data: [studentUser] });
      return Promise.resolve({ data: [] });
    });
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByText('New Board'));
    expect(screen.getByText('Create New Board')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByText('Create New Board')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Assign to student'));
    await screen.findByRole('combobox');
    fireEvent.click(screen.getByText('Close'));
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('closes the delete and bulk-delete dialogs via cancel', async () => {
    mockBoardList(board);
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Delete'));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByText('Cancel'));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Select All'));
    fireEvent.click(screen.getByRole('button', { name: /Delete Selected/ }));
    const bulkDialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(bulkDialog).getByText('Cancel'));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('unselects all boards and hides the bulk delete action', async () => {
    mockBoardList(board);
    renderBoards();
    await screen.findByText('Morning Routine');

    fireEvent.click(screen.getByLabelText('Select All'));
    expect(screen.getByRole('button', { name: /Delete Selected/ })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Select All'));
    expect(screen.queryByText('Delete Selected')).not.toBeInTheDocument();
  });

  it('ignores an empty board name on submit', async () => {
    renderBoards();
    await screen.findByText('Communication Boards');
    fireEvent.click(screen.getByText('New Board'));

    fireEvent.submit(document.querySelector('form') as HTMLFormElement);

    expect(api.post).not.toHaveBeenCalled();
  });
});
