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
        'data.exportFailed': 'Failed to export data. Please try again later.',
        // Kept only so the negative assertion below can tell the old duplicate
        // "server" button apart when the component regresses to two buttons.
        'data.exportServer': 'Server Export',
        'data.exportClientTitle': 'Export data',
        'data.importBoards': 'Import Boards',
        'data.importSuccess': 'Import completed successfully',
        'data.importFailed': 'Import failed: ',
        'data.invalidExportMeta': 'Invalid export: missing meta',
        'data.invalidExportBoards': 'Invalid export: boards must be an array',
        'data.invalidExportAssignedBoards': 'Invalid export: assignedBoards must be an array',
        'data.invalidExportAchievements': 'Invalid export: achievements must be an array',
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

  it('exports the user data through the single export button', async () => {
    get.mockResolvedValue({ data: { boards: [] } });
    render(<DataManagementTab />);

    // The old fake "client vs server" pair was collapsed into one export
    // action: exactly one export button is rendered.
    const exportButtons = screen.getAllByRole('button', { name: 'Export My Data' });
    expect(exportButtons).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Server Export' })).toBeNull();

    fireEvent.click(exportButtons[0]);
    expect(get).toHaveBeenCalledWith('/data/export', { params: { username: 'teacher1' } });
    await waitFor(() =>
      expect(downloadJson).toHaveBeenCalledWith({ boards: [] }, 'aac-data-teacher1.json'),
    );
  });

  it('surfaces a toast when the export request fails', async () => {
    get.mockRejectedValue(new Error('server down'));
    render(<DataManagementTab />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Export My Data' })[0]);

    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith(
        'Failed to export data. Please try again later.',
        'error',
      ),
    );
    expect(downloadJson).not.toHaveBeenCalled();
  });

  it('clears the file input after each selection so re-imports re-fire', async () => {
    post.mockResolvedValue({});
    render(<DataManagementTab />);
    const input = document.getElementById('import-boards-file') as HTMLInputElement;
    const payload = JSON.stringify({
      meta: { version: 1 },
      boards: [],
      assignedBoards: [],
      achievements: [],
    });

    // jsdom dispatches a change event even when the same file is picked again
    // (a real browser suppresses it because the input value did not change),
    // so the red regression is the handler explicitly clearing the value:
    // without ``event.target.value = ''`` a second pick of the same file
    // would never fire onChange. Track writes to the input's value.
    const protoValue = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    );
    let valueResetCount = 0;
    Object.defineProperty(input, 'value', {
      configurable: true,
      get() {
        return protoValue?.get?.call(this);
      },
      set(v: string) {
        if (v === '') valueResetCount += 1;
        protoValue?.set?.call(this, v);
      },
    });

    fireEvent.change(input, { target: { files: [makeFile(payload)] } });
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/data/import', expect.any(Object)),
    );
    expect(addToast).toHaveBeenCalledWith('Import completed successfully', 'success');
    expect(valueResetCount).toBeGreaterThanOrEqual(1);

    // Picking the same file again still runs the import: both dispatches
    // reach the handler because the value was cleared in between.
    fireEvent.change(input, { target: { files: [makeFile(payload)] } });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(valueResetCount).toBeGreaterThanOrEqual(2);
    expect(addToast).toHaveBeenCalledTimes(2);
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
