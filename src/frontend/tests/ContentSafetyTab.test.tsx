import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import i18n, { ensureLocale } from '../src/i18n/index';
import { ContentSafetyTab } from '../src/pages/Settings/ContentSafetyTab';

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock('../src/lib/api', () => ({
  default: mockApi,
  extractError: (err: unknown, fallback: string) => fallback,
}));

const policyPayload = {
  level: 'standard',
  forbidden_topics: ['astronomía'],
  trigger_words: [],
  feature_locks: { block_ai_chat: false, block_board_ai: false },
  sentinel_moderation: false,
  max_response_length: null,
  locked_fields: [],
};

describe('ContentSafetyTab (admin)', () => {
  beforeEach(async () => {
    await ensureLocale('en');
    await i18n.changeLanguage('en');
    vi.clearAllMocks();
    mockApi.get.mockImplementation((url: string) => {
      if (url === '/settings/content-safety/events') {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: policyPayload });
    });
  });

  it('loads and renders the global policy form', async () => {
    render(<ContentSafetyTab />);
    await waitFor(() => {
      expect(mockApi.get).toHaveBeenCalledWith('/settings/content-safety');
    });
    expect(await screen.findByLabelText('Filter level')).toBeInTheDocument();
    expect(screen.getByText('astronomía')).toBeInTheDocument();
  });

  it('saves the policy through PUT', async () => {
    mockApi.put.mockResolvedValue({ data: policyPayload });
    render(<ContentSafetyTab />);
    const saveButton = await screen.findByRole('button', { name: /Save policy/i });
    fireEvent.click(saveButton);
    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalledWith('/settings/content-safety', expect.any(Object));
    });
  });

  it('purges AI symbols after confirmation', async () => {
    mockApi.delete.mockResolvedValue({ data: { deleted: 3 } });
    render(<ContentSafetyTab />);
    // There are two buttons with the same label (the trigger and the dialog
    // confirm); use the last one for the trigger and scope the confirm
    // inside the dialog.
    const purgeButtons = await screen.findAllByRole('button', { name: /Delete AI-generated pictograms/i });
    fireEvent.click(purgeButtons[0]);
    const dialog = await screen.findByRole('alertdialog');
    const confirm = within(dialog).getByRole('button', { name: /Delete AI-generated pictograms/i });
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(mockApi.delete).toHaveBeenCalledWith('/settings/content-safety/ai-symbols');
    });
  });

  it('loads the events log', async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url === '/settings/content-safety/events') {
        return Promise.resolve({
          data: [
            {
              id: 1,
              surface: 'chat',
              direction: 'input',
              verdict: 'redirected',
              matched: ['sexo'],
              detail: null,
              created_at: '2026-09-01T00:00:00Z',
            },
          ],
        });
      }
      return Promise.resolve({ data: policyPayload });
    });
    render(<ContentSafetyTab />);
    expect(await screen.findByText('chat')).toBeInTheDocument();
    expect(screen.getByText('sexo')).toBeInTheDocument();
  });
});
