import { fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n, { ensureLocale } from '../src/i18n/index';
import { LearningChatPanel } from '../src/components/learning/LearningChatPanel';

vi.mock('../src/components/learning/LearningInputRow', () => ({
  LearningInputRow: () => <div data-testid="learning-input-row" />,
}));

vi.mock('../src/components/learning/LearningMessageList', () => ({
  LearningMessageList: () => <div data-testid="learning-message-list" />,
}));

vi.mock('../src/components/learning/LearningQuestionCard', () => ({
  LearningQuestionCard: () => null,
}));

const baseProps = {
  messages: [],
  isLoading: false,
  error: null,
  isStartingSession: false,
  sessionStartError: null,
  currentSession: { success: true, session_id: 42 },
  currentQuestion: null,
  revealed: null,
  progress: null,
  onAnswerQuestion: vi.fn(),
  onEndSession: vi.fn(),
  isAdmin: false,
  showAdminReasoning: false,
  onShowAdminReasoningChange: vi.fn(),
  onStartSession: vi.fn(),
  editingMessageIndex: null,
  onEditMessage: vi.fn(),
  onUpdateSymbols: vi.fn(),
  onCancelEdit: vi.fn(),
  input: '',
  onInputChange: vi.fn(),
  onSubmit: vi.fn(),
  voiceEnabled: false,
  isRecording: false,
  hasRecording: false,
  startRecording: vi.fn(),
  stopRecording: vi.fn(),
  sendRecording: vi.fn(),
  discardRecording: vi.fn(),
};

describe('LearningChatPanel End Session confirmation', () => {
  beforeEach(async () => {
    await ensureLocale('en');
    await i18n.changeLanguage('en');
    vi.clearAllMocks();
  });

  it('makes the scrollable conversation history keyboard-focusable', () => {
    render(<LearningChatPanel {...baseProps} />);

    const conversation = screen.getByRole('log', { name: /Conversation history/i });
    expect(conversation).toHaveAttribute('tabindex', '0');
    conversation.focus();
    expect(conversation).toHaveFocus();
  });

  it('scrolls the conversation to the newest content', async () => {
    const { rerender } = render(<LearningChatPanel {...baseProps} />);
    const conversation = screen.getByRole('log', { name: /Conversation history/i });
    const scrollTop = vi.spyOn(conversation, 'scrollTop', 'set');

    rerender(<LearningChatPanel {...baseProps} messages={[{ role: 'assistant', content: 'New message' }]} />);

    await waitFor(() => expect(scrollTop).toHaveBeenCalledWith(conversation.scrollHeight));
  });

  it('opens an inline confirmation popover instead of calling immediately', () => {
    render(<LearningChatPanel {...baseProps} />);

    const trigger = screen.getByRole('button', { name: 'End Session' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(baseProps.onEndSession).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
  });

  it('cancels without ending the session', () => {
    render(<LearningChatPanel {...baseProps} />);

    fireEvent.click(screen.getByRole('button', { name: 'End Session' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'End Session' })).toHaveFocus();
    expect(baseProps.onEndSession).not.toHaveBeenCalled();
  });

  it('ends the session only after the inline confirmation', () => {
    render(<LearningChatPanel {...baseProps} />);

    fireEvent.click(screen.getByRole('button', { name: 'End Session' }));
    const confirmation = screen.getByRole('dialog');
    fireEvent.click(
      within(confirmation).getByRole('button', { name: 'End Session' }),
    );

    expect(confirmation).not.toBeInTheDocument();
    expect(baseProps.onEndSession).toHaveBeenCalledTimes(1);
  });

  it('dismisses the popover with Escape', () => {
    render(<LearningChatPanel {...baseProps} />);

    fireEvent.click(screen.getByRole('button', { name: 'End Session' }));
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'End Session' })).toHaveFocus();
    expect(baseProps.onEndSession).not.toHaveBeenCalled();
  });
});
