import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n, { ensureLocale } from '../src/i18n/index';
import { LearningHeader } from '../src/components/learning/LearningHeader';

const baseProps = {
  showHistory: false,
  onToggleHistory: vi.fn(),
  symbolView: false,
  onToggleSymbolView: vi.fn(),
  selectedModeKey: 'practice',
  onModeChange: vi.fn(),
  availableModes: [{ id: 1, name: 'Practice', key: 'practice', description: 'Practice' }],
  difficultyOverride: 'adaptive' as const,
  onDifficultyChange: vi.fn(),
  providerInUse: undefined,
  providerNotice: null,
  voiceEnabled: false,
  onToggleVoice: vi.fn(),
  onNewQuestion: vi.fn(),
  canAskQuestion: true,
};

describe('LearningHeader difficulty override', () => {
  beforeEach(async () => {
    await ensureLocale('en');
    await i18n.changeLanguage('en');
    vi.clearAllMocks();
  });

  it('renders Adaptive by default and reports a fixed difficulty selection', () => {
    render(<LearningHeader {...baseProps} />);

    const difficulty = screen.getByRole('combobox', { name: /Difficulty/i });
    expect(difficulty).toHaveValue('adaptive');

    fireEvent.change(difficulty, { target: { value: 'advanced' } });
    expect(baseProps.onDifficultyChange).toHaveBeenCalledWith('advanced');
  });

  it('offers adaptive, basic, intermediate, and advanced options', () => {
    render(<LearningHeader {...baseProps} />);

    const difficulty = screen.getByRole('combobox', { name: /Difficulty/i });
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(
      expect.arrayContaining(['Adaptive', 'Basic', 'Intermediate', 'Advanced']),
    );
    expect(difficulty).toHaveAttribute('title', 'Choose a fixed level or let the AI adapt');
  });
});
