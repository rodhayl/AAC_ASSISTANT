import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BoardEditorToolbar } from '../src/components/board/BoardEditorToolbar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

function renderToolbar(overrides: Partial<Parameters<typeof BoardEditorToolbar>[0]> = {}) {
  const props = {
    boardName: 'Board',
    showSuggestions: false,
    aiLoading: false,
    status: { playable: true, progress: 100, needed: 0, count: 4, threshold: 2 },
    gridPreset: '4x5',
    hasChanges: false,
    hasSymbols: true,
    isBusy: false,
    onLoadSuggestions: vi.fn(),
    onSpeakMode: vi.fn(),
    onOpenSettings: vi.fn(),
    onGridChange: vi.fn(),
    onSave: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  };
  return render(<BoardEditorToolbar {...props} />);
}

describe('BoardEditorToolbar grid select', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the current non-preset grid as the selected option', () => {
    renderToolbar({ gridPreset: '3x6' });
    const select = screen.getByLabelText('layout') as HTMLSelectElement;
    expect(select.value).toBe('3x6');
    expect(screen.getByRole('option', { name: '3x6' })).toBeInTheDocument();
  });

  it('keeps preset grids unchanged', () => {
    renderToolbar({ gridPreset: '4x4' });
    const select = screen.getByLabelText('layout') as HTMLSelectElement;
    expect(select.value).toBe('4x4');
    expect(screen.queryByRole('option', { name: '3x6' })).not.toBeInTheDocument();
  });

  it('forwards grid changes to the change handler', () => {
    const onGridChange = vi.fn();
    renderToolbar({ onGridChange });
    const select = screen.getByLabelText('layout');
    fireEvent.change(select, { target: { value: '3x3' } });
    expect(onGridChange).toHaveBeenCalledWith('3x3');
  });
});
