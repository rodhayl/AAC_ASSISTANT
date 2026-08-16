import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n, { ensureLocale } from '../src/i18n/index';
import {
  LearningMessageList,
  type LearningMessage,
} from '../src/components/learning/LearningMessageList';

vi.mock('../src/components/SymbolMessageEditor', () => ({
  SymbolMessageEditor: () => <div data-testid="symbol-message-editor" />,
}));

function renderMessages(messages: LearningMessage[]) {
  return render(
    <LearningMessageList
      messages={messages}
      editingMessageIndex={null}
      onEditMessage={vi.fn()}
      onUpdateSymbols={vi.fn()}
      onCancelEdit={vi.fn()}
    />,
  );
}

describe('LearningMessageList fallback source badge', () => {
  beforeEach(async () => {
    await ensureLocale('en');
    await i18n.changeLanguage('en');
  });

  it('shows the local-generation badge on a fallback assistant message', () => {
    renderMessages([
      { role: 'assistant', content: 'Showing a practice question?', source: 'fallback' },
    ]);

    const badge = screen.getByTestId('fallback-source-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute('role', 'status');
    expect(badge.textContent).toContain('generated locally');
    expect(screen.getByText('Showing a practice question?')).toBeInTheDocument();
  });

  it('does not show the badge on an LLM assistant message', () => {
    renderMessages([
      { role: 'assistant', content: 'Great job!', source: 'llm' },
    ]);

    expect(screen.queryByTestId('fallback-source-badge')).not.toBeInTheDocument();
  });

  it('does not show the badge on legacy messages without a source', () => {
    renderMessages([{ role: 'assistant', content: 'Old message' }]);

    expect(screen.queryByTestId('fallback-source-badge')).not.toBeInTheDocument();
  });

  it('never shows the badge on user messages', () => {
    renderMessages([
      { role: 'user', content: 'My answer' },
      { role: 'user', content: 'Symbols', symbolImages: [{ label: 'dog' }] },
    ]);

    expect(screen.queryByTestId('fallback-source-badge')).not.toBeInTheDocument();
  });

  it('shows the badge alongside a fallback symbol message', () => {
    renderMessages([
      {
        role: 'assistant',
        content: 'Tell me about the dog',
        source: 'fallback',
        symbolImages: [{ label: 'dog' }],
      },
    ]);

    expect(screen.getByTestId('fallback-source-badge')).toBeInTheDocument();
  });
});
