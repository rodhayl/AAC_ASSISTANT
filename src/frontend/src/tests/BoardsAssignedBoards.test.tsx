import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { Boards } from '../pages/Boards';
import { useBoardStore } from '../store/boardStore';
import { useAuthStore } from '../store/authStore';
import { useSettingsStore } from '../store/settingsStore';
import api from '../lib/api';

vi.mock('../lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../store/authStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('../store/settingsStore', () => ({
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

  beforeEach(() => {
    vi.clearAllMocks();
    useBoardStore.setState({
      boards: [],
      assignedBoards: [],
      isLoading: false,
      error: null,
      lastFetchTime: null,
    });
    vi.mocked(useAuthStore).mockReturnValue({
      user: {
        id: 10,
        username: 'student',
        display_name: 'Student',
        user_type: 'student',
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
      },
    } as ReturnType<typeof useAuthStore>);
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
});
