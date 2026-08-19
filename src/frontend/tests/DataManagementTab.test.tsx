import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataManagementTab } from '../src/pages/Settings/DataManagementTab';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const addToast = vi.hoisted(() => vi.fn());
const downloadJson = vi.hoisted(() => vi.fn());

vi.mock('../src/lib/api', () => ({
  default: { get, post },
}));

vi.mock('../src/store/toastStore', () => ({
  useToastStore: (selector: (state: { addToast: typeof addToast }) => unknown) =>
    selector({ addToast }),
}));

vi.mock('../src/lib/download', () => ({
  downloadJson,
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: { user: { username: string; user_type: string } }) => unknown) =>
    selector({ user: { username: 'teacher1', user_type: 'teacher' } }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => {
      const table: Record<string, string> = {
        'data.exportClient': 'Export My Data',
        'data.exportServer': 'Server Export',
        'data.exportClientTitle': 'Export client',
        'data.exportServerTitle': 'Export server',
        'data.importBoards': 'Import Boards',
        'data.importSuccess': 'Import completed successfully',
        'data.importFailed': 'Import failed: ',
        'data.invalidExportMeta': 'Invalid export: missing meta',
        'data.invalidExportBoards': 'Invalid export: boards must be an array',
        'data.invalidExportAssignedBoards': 'Invalid export: assignedBoards must be an array',
        'data.invalidExportAchievements': 'Invalid export: achievements must be an array',
        'data.exportServerFailed': 'Failed to export from server',
        'errors.unknownError': 'Unknown error',
      };
      return table[key] ?? defaultValue ?? key;
    },
  }),
}));

// jsdom does not implement File.prototype.text(), so provide it explicitly.
function makeFile(content: string): File {
  const file = new File([content], 'data.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', {
    value: () => Promise.resolve(content),
  });
  return file;
}

describe('DataManagementTab', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    addToast.mockReset();
    downloadJson.mockReset();
  });

  it('exports the user data as a client-side JSON download', async () => {
    get.mockResolvedValue({ data: { boards: [] } });
    render(<DataManagementTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Export My Data' }));
    expect(get).toHaveBeenCalledWith('/data/export', { params: { username: 'teacher1' } });
    await waitFor(() =>
      expect(downloadJson).toHaveBeenCalledWith({ boards: [] }, 'aac-data-teacher1.json'),
    );
  });

  it('shows a localized validation error when importing a file without meta', async () => {
    render(<DataManagementTab />);
    const input = document.getElementById('import-boards-file') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile('{"boards": []}')] } });

    await waitFor(() => expect(post).not.toHaveBeenCalled());
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith('Import failed: Invalid export: missing meta', 'error'),
    );
  });

  it('shows a localized validation error when boards is not an array', async () => {
    render(<DataManagementTab />);
    const input = document.getElementById('import-boards-file') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [makeFile('{"meta": {}, "boards": "nope"}')] },
    });

    await waitFor(() => expect(post).not.toHaveBeenCalled());
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith(
        'Import failed: Invalid export: boards must be an array',
        'error',
      ),
    );
  });

  it('imports a valid file and confirms success', async () => {
    post.mockResolvedValue({});
    render(<DataManagementTab />);
    const input = document.getElementById('import-boards-file') as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [
          makeFile(
            JSON.stringify({
              meta: { version: 1 },
              boards: [],
              assignedBoards: [],
              achievements: [],
            }),
          ),
        ],
      },
    });

    await waitFor(() => expect(post).toHaveBeenCalledWith('/data/import', expect.any(Object)));
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith('Import completed successfully', 'success'),
    );
  });
});
