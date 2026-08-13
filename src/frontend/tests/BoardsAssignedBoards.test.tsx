import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';

import { Boards } from '../src/pages/Boards';
import { useBoardStore } from '../src/store/boardStore';
import { useAuthStore } from '../src/store/authStore';
import { useSettingsStore } from '../src/store/settingsStore';
import api from '../src/lib/api';

vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('../src/store/settingsStore', () => ({
  useSettingsStore: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
}));

describe('Boards assigned-board display', () => {
  const assignedBoard = {
    id: 42,
    user_id: 10,
    name: 'Assigned Board',
    description: 'A board assigned by a teacher',
    category: 'general',
    is_public: false,
    is_template: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    symbols: [],
  };

  afterEach(() => {
    vi.useRealTimers();
  });

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
    });
    const authState = {
      user: {
        id: 10,
        username: 'student',
        display_name: 'Student',
        user_type: 'student' as const,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
      },
    };
    vi.mocked(useAuthStore).mockImplementation((selector?: (state: typeof authState) => unknown) =>
      (selector ? selector(authState) : authState) as ReturnType<typeof useAuthStore>,
    );
    vi.mocked(useSettingsStore).mockReturnValue({
      aiSettings: null,
      fetchAISettings: vi.fn().mockResolvedValue(undefined),
    } as ReturnType<typeof useSettingsStore>);
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/boards/assigned') return Promise.resolve({ data: [assignedBoard] });
      if (url === '/boards/') return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
  });

  it('renders assigned boards for students without personal boards', async () => {
    render(
      <MemoryRouter>
        <Boards />
      </MemoryRouter>,
    );

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/boards/assigned',
      { params: { student_id: 10 } },
    ));
    expect(await screen.findByText('Assigned Board')).toBeInTheDocument();
  });

  it('does not refetch assigned boards when searching personal boards', async () => {
    render(
      <MemoryRouter>
        <Boards />
      </MemoryRouter>,
    );

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/boards/assigned',
      { params: { student_id: 10 } },
    ));
    const assignedCallsBeforeSearch = vi.mocked(api.get).mock.calls.filter(
      ([url]) => url === '/boards/assigned',
    ).length;

    vi.useFakeTimers();
    fireEvent.change(screen.getByRole('textbox', { name: 'searchPlaceholder' }), {
      target: { value: 'school' },
    });
    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });

    const assignedCallsAfterSearch = vi.mocked(api.get).mock.calls.filter(
      ([url]) => url === '/boards/assigned',
    ).length;
    expect(assignedCallsAfterSearch).toBe(assignedCallsBeforeSearch);
  });
});
