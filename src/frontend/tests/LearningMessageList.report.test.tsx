import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n, { ensureLocale } from '../src/i18n/index';
import { LearningMessageList } from '../src/components/learning/LearningMessageList';

vi.mock('../src/lib/api', () => ({
  default: { post: vi.fn().mockResolvedValue({ data: { success: true } }) },
  extractError: (err: unknown, fallback: string) => fallback,
}));

const api = (await import('../src/lib/api')).default;

const baseProps = {
  messages: [
    { role: 'user' as const, content: 'Hola' },
    { role: 'assistant' as const, content: '¡Hola! ¿Qué quieres aprender hoy?' },
  ],
  editingMessageIndex: null,
  sessionId: 42,
  onEditMessage: vi.fn(),
  onUpdateSymbols: vi.fn(),
  onCancelEdit: vi.fn(),
};

describe('LearningMessageList report button', () => {
  beforeEach(async () => {
    await ensureLocale('en');
    await i18n.changeLanguage('en');
    vi.clearAllMocks();
  });

  it('shows a report action on assistant messages only', () => {
    render(<LearningMessageList {...baseProps} />);
    const reportButtons = screen.getAllByRole('button', { name: /Report/i });
    expect(reportButtons).toHaveLength(1);
  });

  it('posts a report and marks the message as reported (no double-report)', async () => {
    render(<LearningMessageList {...baseProps} />);
    const reportButton = screen.getByRole('button', { name: /Report/i });
    fireEvent.click(reportButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/learning/42/report');
    });
    // The button flips to the reported state and is disabled.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Reported/i })).toBeDisabled();
    });
  });

  it('does not render a report action without a session', () => {
    render(<LearningMessageList {...baseProps} sessionId={null} />);
    expect(screen.queryByRole('button', { name: /Report/i })).toBeNull();
  });
});
