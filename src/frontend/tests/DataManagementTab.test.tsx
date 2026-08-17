import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataManagementTab } from '../src/pages/Settings/DataManagementTab';
import { useToastStore } from '../src/store/toastStore';

const get = vi.hoisted(() => vi.fn());
const post = vi.hoisted(() => vi.fn());
const downloadJson = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    username: 'admin1',
    display_name: 'Admin',
    email: null as string | null,
    user_type: 'admin',
  },
}));

vi.mock('../src/lib/api', () => ({
  default: { get, post },
  extractError: (error: { message?: string } | undefined, fallback: string) =>
    error?.message || fallback,
}));

vi.mock('../src/lib/download', () => ({ downloadJson }));

vi.mock('../src/store/authStore', () => {
  const useAuthStore = (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState;
  useAuthStore.setState = vi.fn();
  return { useAuthStore };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => {
      const table: Record<string, string> = {
        'data.title': 'Data',
        'data.subtitle': 'Manage your data',
        'data.exportClient': 'Export',
        'data.exportServer': 'Server export',
        'data.importBoards': 'Import boards',
        'data.importSuccess': 'Imported',
        'data.importFailed': 'Import failed: ',
        'data.exportServerFailed': 'Server export failed',
      };
      return table[key] ?? defaultValue ?? key;
    },
  }),
}));

describe('DataManagementTab', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    downloadJson.mockReset();
    useToastStore.setState({ toasts: [] });
    authState.user = {
      id: 1,
      username: 'admin1',
      display_name: 'Admin',
      email: null,
      user_type: 'admin',
    };
  });

  it('exports client-side data for a staff user', async () => {
    get.mockResolvedValue({ data: { boards: [] } });
    render(<DataManagementTab />);

    fireEvent.click(screen.getByTitle('data.exportClientTitle'));

    await waitFor(() => expect(downloadJson).toHaveBeenCalled());
    expect(get).toHaveBeenCalledWith('/data/export', {
      params: { username: 'admin1' },
    });
    expect(downloadJson).toHaveBeenCalledWith(
      { boards: [] },
      'aac-data-admin1.json',
    );
  });

  it('exports server-side data with the server suffix', async () => {
    get.mockResolvedValue({ data: { boards: [] } });
    render(<DataManagementTab />);

    fireEvent.click(screen.getByTitle('data.exportServerTitle'));

    await waitFor(() =>
      expect(downloadJson).toHaveBeenCalledWith({ boards: [] }, 'aac-data-admin1-server.json'),
    );
  });

  it('shows an error toast when the server export fails', async () => {
    get.mockRejectedValue(new Error('down'));
    render(<DataManagementTab />);

    fireEvent.click(screen.getByTitle('data.exportServerTitle'));

    await waitFor(() =>
      expect(
        useToastStore.getState().toasts.some((t) => t.message === 'Server export failed'),
      ).toBe(true),
    );
  });

  it('imports a valid export file', async () => {
    post.mockResolvedValue({});
    render(<DataManagementTab />);

    // jsdom File lacks .text(); use a File-compatible object.
    const file = {
      name: 'export.json',
      text: async () =>
        JSON.stringify({ meta: {}, boards: [], assignedBoards: [], achievements: [] }),
    };
    fireEvent.change(screen.getByLabelText('Import boards', { hidden: true }), {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(
        useToastStore.getState().toasts.some((t) => t.message === 'Imported'),
      ).toBe(true),
    );
    expect(post).toHaveBeenCalledWith(
      '/data/import',
      expect.objectContaining({ meta: {}, boards: [] }),
    );
  });

  it('shows an error toast for malformed export files', async () => {
    render(<DataManagementTab />);

    const file = {
      name: 'broken.json',
      text: async () => 'not json at all',
    };
    fireEvent.change(screen.getByLabelText('Import boards', { hidden: true }), {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(
        useToastStore.getState().toasts.some((t) => t.message.includes('Import failed')),
      ).toBe(true),
    );
    expect(post).not.toHaveBeenCalled();
  });

  it('hides staff-only actions for a student', () => {
    authState.user = {
      id: 2,
      username: 'student1',
      display_name: 'Student',
      email: null,
      user_type: 'student',
    };
    render(<DataManagementTab />);

    expect(screen.queryByTitle('data.exportServerTitle')).not.toBeInTheDocument();
    expect(screen.getByTitle('data.exportClientTitle')).toBeInTheDocument();
  });
});
